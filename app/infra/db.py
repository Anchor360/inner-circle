import os
import psycopg2


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "mic"),
        user=os.getenv("DB_USER", "mic"),
        password=os.getenv("DB_PASSWORD", "mic_app_pass"),
    )