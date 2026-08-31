import os
import sys
from datetime import datetime

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from database import get_connection

app = Flask(__name__, template_folder="../templates")
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "Akash Leaks")

# Maximum upload size: 100 MB
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


# Allowed file types
ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/ogg"
}


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

    return render_template(
        "index.html",
        posts=posts
    )


# =========================================================
# UPLOAD IMAGE / VIDEO
# =========================================================

@app.route("/upload", methods=["POST"])
def upload():

    submitted_password = request.form.get("password", "").strip()
    if submitted_password != UPLOAD_PASSWORD:
        return "Incorrect password", 403

    if "file" not in request.files:
        return "No file selected", 400

    file = request.files["file"]

    if file.filename == "":
        return "No file selected", 400

    # Check MIME type
    if file.content_type not in ALLOWED_TYPES:
        return "File type not allowed", 400

    # Get and validate description/title for compatibility
    description = request.form.get("description", "").strip() or request.form.get("title", "").strip()
    if not description:
        return "Description is required", 400

    # Read file as binary
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
        
        # Redirect back to home after successful upload

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
                SELECT file_data, file_type
                FROM posts
                WHERE id = %s
            """, (post_id,))

            post = cursor.fetchone()

    finally:

        connection.close()

    if not post:
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
    <p>Maximum file size is 100 MB.</p>
    <a href="/">Go back</a>
    """, 413


# =========================================================
# RUN APPLICATION
# =========================================================
