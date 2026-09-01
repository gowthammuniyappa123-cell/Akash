import os
import sys
from datetime import datetime

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from database import get_connection

app = Flask(__name__, template_folder="../templates", static_folder="../static")
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "Akash Leaks")

# Maximum upload size: 250 MB (large enough for common videos)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

# Allowed file types
ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/ogg",
    "video/quicktime",
    "video/x-matroska",
    "video/x-msvideo"
}


def ensure_posts_blob_columns():
    """Add blob metadata columns when they don't already exist."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'posts'
            """)
            existing = {row["column_name"] for row in cursor.fetchall()}

            column_statements = {
                "file_url": "ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_url TEXT",
                "file_path": "ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_path TEXT",
                "file_size": "ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_size BIGINT",
                "file_mime_type": "ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_mime_type TEXT",
            }

            for column_name, statement in column_statements.items():
                if column_name not in existing:
                    cursor.execute(statement)

        connection.commit()
    finally:
        connection.close()


ensure_posts_blob_columns()


def format_time_ago(created_at):
    """Convert timestamp to 'time ago' format"""
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

    now = datetime.utcnow()
    if created_at.tzinfo is None:
        diff = now - created_at
    else:
        diff = now - created_at.replace(tzinfo=None)

    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago" if minutes > 1 else "1m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago" if hours > 1 else "1h ago"
    else:
        days = int(seconds / 86400)
        return f"{days}d ago" if days > 1 else "1d ago"


def record_post(description, file_name, file_type, file_url=None, file_path=None, file_size=None):
    """Insert a metadata-only post entry, keeping DB payload small."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'posts'
            """)
            columns = {row["column_name"] for row in cursor.fetchall()}

            insert_cols = ["title"]
            values = [description]

            if "file_name" in columns:
                insert_cols.append("file_name")
                values.append(file_name)
            if "file_type" in columns:
                insert_cols.append("file_type")
                values.append(file_type)
            if "file_url" in columns:
                insert_cols.append("file_url")
                values.append(file_url)
            if "file_path" in columns:
                insert_cols.append("file_path")
                values.append(file_path)
            if "file_size" in columns:
                insert_cols.append("file_size")
                values.append(file_size)
            if "file_mime_type" in columns:
                insert_cols.append("file_mime_type")
                values.append(file_type)

            placeholders = ", ".join(["%s"] * len(insert_cols))
            column_sql = ", ".join(insert_cols)

            cursor.execute(
                f"INSERT INTO posts ({column_sql}) VALUES ({placeholders})",
                tuple(values),
            )

        connection.commit()
    finally:
        connection.close()


# =========================================================
# HOME / DASHBOARD
# =========================================================

@app.route("/")
def index():

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    title,
                    file_name,
                    file_type,
                    file_url,
                    file_path,
                    file_size,
                    likes,
                    created_at
                FROM posts
                ORDER BY created_at DESC
            """)

            posts = cursor.fetchall()
            
            # Format time ago for display
            for post in posts:
                post['time_ago'] = format_time_ago(post['created_at'])

    finally:

        connection.close()

    blob_upload_enabled = bool(
        os.getenv("BLOB_READ_WRITE_TOKEN")
        or os.getenv("BLOB_STORE_ID")
        or os.getenv("VERCEL_OIDC_TOKEN")
    )

    return render_template(
        "index.html",
        posts=posts,
        blob_upload_enabled=blob_upload_enabled,
        upload_password=UPLOAD_PASSWORD,
    )


# =========================================================
# UPLOAD IMAGE / VIDEO
# =========================================================

@app.route("/upload", methods=["POST"])
def upload():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        submitted_password = str(payload.get("password", "")).strip()
        description = str(payload.get("description", "") or payload.get("title", "")).strip()
        file_url = payload.get("file_url") or payload.get("url")
        file_path = payload.get("file_path") or payload.get("pathname")
        file_name = payload.get("file_name") or payload.get("filename")
        file_type = payload.get("file_type") or payload.get("content_type")
        file_size = payload.get("file_size") or payload.get("size")

        if submitted_password != UPLOAD_PASSWORD:
            return jsonify({"error": "Incorrect password"}), 403
        if not file_url:
            return jsonify({"error": "Missing file URL"}), 400
        if not description:
            return jsonify({"error": "Description is required"}), 400
        if not file_name:
            return jsonify({"error": "Missing file name"}), 400
        if file_type and file_type not in ALLOWED_TYPES:
            return jsonify({"error": "File type not allowed"}), 400

        try:
            file_size = int(file_size) if file_size is not None else None
        except (TypeError, ValueError):
            file_size = None

        record_post(
            description=description,
            file_name=file_name,
            file_type=file_type or "application/octet-stream",
            file_url=file_url,
            file_path=file_path,
            file_size=file_size,
        )
        return jsonify({"success": True}), 200

    submitted_password = request.form.get("password", "").strip()
    if submitted_password != UPLOAD_PASSWORD:
        return "Incorrect password", 403

    if "file" not in request.files:
        return "No file selected", 400

    file = request.files["file"]

    if file.filename == "":
        return "No file selected", 400

    if file.content_type not in ALLOWED_TYPES:
        filename = file.filename.lower()
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".ogg", ".mov", ".mkv", ".avi"}
        if not filename or os.path.splitext(filename)[1] not in allowed_extensions:
            return "File type not allowed", 400

    description = request.form.get("description", "").strip() or request.form.get("title", "").strip()
    if not description:
        return "Description is required", 400

    file_data = file.read()
    if not file_data:
        return "Empty file", 400

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO posts
                (
                    title,
                    file_data,
                    file_type,
                    file_name
                )
                VALUES (%s, %s, %s, %s)
            """, (
                description,
                file_data,
                file.content_type,
                file.filename
            ))
        connection.commit()
    finally:
        connection.close()

    return redirect(url_for("index"))


# =========================================================
# DISPLAY IMAGE / VIDEO
# =========================================================
# GET /media/<post_id> - returns binary file data with correct MIME type

@app.route("/media/<int:post_id>")
def media(post_id):

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT file_data, file_type, file_url, file_name
                FROM posts
                WHERE id = %s
            """, (post_id,))

            post = cursor.fetchone()

    finally:

        connection.close()

    if not post:
        return "File not found", 404

    if post.get("file_url"):
        return redirect(post["file_url"], code=302)

    if not post.get("file_data"):
        return "File not found", 404

    return Response(
        post["file_data"],
        mimetype=post["file_type"]
    )


# =========================================================
# LIKE POST
# =========================================================

@app.route("/like/<int:post_id>", methods=["POST"])
def like(post_id):

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            # Increase like count
            cursor.execute("""
                UPDATE posts
                SET likes = likes + 1
                WHERE id = %s
            """, (post_id,))

            if cursor.rowcount == 0:
                return jsonify({
                    "success": False,
                    "message": "Post not found"
                }), 404

            # Get updated count
            cursor.execute("""
                SELECT likes
                FROM posts
                WHERE id = %s
            """, (post_id,))

            result = cursor.fetchone()

        connection.commit()

    finally:

        connection.close()

    return jsonify({
        "success": True,
        "likes": result["likes"]
    })


# =========================================================
# DELETE POST
# =========================================================

@app.route("/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):

    connection = get_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT file_url, file_path
                FROM posts
                WHERE id = %s
            """, (post_id,))
            post = cursor.fetchone()

            if post:
                cursor.execute("""
                    DELETE FROM posts
                    WHERE id = %s
                """, (post_id,))

        connection.commit()

    finally:

        connection.close()

    return jsonify({"success": True})


# =========================================================
# ERROR: FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return """
    <h2>File too large</h2>
    <p>Maximum file size is 250 MB.</p>
    <a href="/">Go back</a>
    """, 413


# =========================================================
# RUN APPLICATION
# =========================================================
