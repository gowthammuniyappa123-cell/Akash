import os

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


load_dotenv()


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("Missing required DATABASE_URL environment variable")

    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
    )