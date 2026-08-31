import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


project_root = Path(__file__).resolve().parent
load_dotenv(project_root / ".env", override=False)


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "Missing DATABASE_URL. Create a .env file in the project root with DATABASE_URL=postgresql://... or set it in Vercel."
        )

    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
    )