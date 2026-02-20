#!/usr/bin/env python3
import csv, hashlib, io, os, sys
from datetime import datetime, timezone
import psycopg2, requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE_URL = "https://media.bis.gov/sites/default/files/documents/denied-persons-list.txt"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "mic"),
    "user": os.getenv("DB_USER", "mic_app"),
    "password": os.getenv("DB_PASSWORD", "mic_password"),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def fetch_data():
    print(f"Fetching BIS DPL...")
    r = requests.get(SOURCE_URL, timeout=30, verify=False)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content):,} bytes")
    return r.text

def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def parse_date(s):
    s = s.strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bis_dpl (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                street_address TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                postal_code TEXT,
                effective_date DATE,
                expiration_date DATE,
                standard_order TEXT,
                last_update DATE,
                action TEXT,
                row_hash TEXT NOT NULL UNIQUE,
                source_url TEXT NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bis_dpl_name ON bis_dpl(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bis_dpl_country ON bis_dpl(country)")
        conn.commit()
    print("  Table bis_dpl ready.")

def ingest(text, conn):
    reader = csv.DictReader(io.StringIO(text))
    inserted = skipped = 0
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        for row in reader:
            name = row.get("Name", "").strip()
            if not name:
                continue
            row_data = "|".join([
                name,
                row.get("Street_Address", "").strip(),
                row.get("City", "").strip(),
                row.get("Country", "").strip(),
                row.get("Effective_Date", "").strip(),
            ])
            row_hash = compute_hash(row_data)
            try:
                cur.execute("""
                    INSERT INTO bis_dpl (
                        name, street_address, city, state, country, postal_code,
                        effective_date, expiration_date, standard_order,
                        last_update, action, row_hash, source_url, ingested_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (row_hash) DO NOTHING
                """, (
                    name,
                    row.get("Street_Address", "").strip() or None,
                    row.get("City", "").strip() or None,
                    row.get("State", "").strip() or None,
                    row.get("Country", "").strip() or None,
                    row.get("Postal_Code", "").strip() or None,
                    parse_date(row.get("Effective_Date", "")),
                    parse_date(row.get("Expiration_Date", "")),
                    row.get("Standard_Order", "").strip() or None,
                    parse_date(row.get("Last_Update", "")),
                    row.get("Action", "").strip() or None,
                    row_hash, SOURCE_URL, now,
                ))
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"  ERROR on '{name}': {e}")
                conn.rollback()
        conn.commit()
    return inserted, skipped

def main():
    print("=== BIS Denied Persons List Ingestion ===")
    conn = get_connection()
    print("  DB connection OK")
    ensure_table(conn)
    text = fetch_data()
    inserted, skipped = ingest(text, conn)
    print(f"\n✅ Done. Inserted: {inserted:,} | Skipped: {skipped:,}")
    conn.close()

if __name__ == "__main__":
    main()