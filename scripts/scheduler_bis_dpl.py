import requests
import psycopg2
import os
import csv
import io
import hashlib
import urllib3
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

DPL_URL = "https://media.bis.gov/sites/default/files/documents/denied-persons-list.txt"
INTERVAL_SECONDS = 4 * 60 * 60  # 4 hours

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "mic"),
        user=os.getenv("DB_USER", "mic_app"),
        password=os.getenv("DB_PASSWORD")
    )

def get_last_hash(cur):
    cur.execute("""
        SELECT payload->>'content_hash'
        FROM events
        WHERE event_type = 'bis_dpl_ingestion'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    return row[0] if row else None

def log_event(cur, status, content_hash, entries_updated, message):
    cur.execute("""
        INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, payload)
        VALUES (gen_random_uuid(), 'bis_dpl_ingestion', 'system', 'bis_dpl', 'scheduler', 'bis_scheduler', %s)
    """, (
        __import__('json').dumps({
            "status": status,
            "content_hash": content_hash,
            "entries_updated": entries_updated,
            "message": message
        }),
    ))

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

def run_once():
    now = datetime.now(timezone.utc)
    print(f"[{now}] Starting BIS DPL check...")

    try:
        response = requests.get(DPL_URL, timeout=60, verify=False)
        raw_text = response.text
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        print(f"Downloaded {len(raw_text):,} bytes | Hash: {content_hash[:16]}...")

        conn = get_conn()
        cur = conn.cursor()

        last_hash = get_last_hash(cur)

        if last_hash == content_hash:
            print("Hash unchanged — no update needed.")
            log_event(cur, "skipped", content_hash, 0, "Hash matched last ingestion. No update performed.")
            conn.commit()
            cur.close()
            conn.close()
            return

        print("Hash changed — ingesting updated list...")
        reader = csv.DictReader(io.StringIO(raw_text))
        inserted = 0

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
            row_hash = hashlib.sha256(row_data.encode()).hexdigest()

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
                row_hash, DPL_URL,
                datetime.now(timezone.utc),
            ))
            if cur.rowcount > 0:
                inserted += 1

        log_event(cur, "updated", content_hash, inserted, f"Ingested {inserted} new entries from BIS DPL.")
        conn.commit()
        cur.close()
        conn.close()
        print(f"Done. Inserted: {inserted} new entries.")

    except Exception as e:
        print(f"[ERROR] {e}")
        try:
            conn = get_conn()
            cur = conn.cursor()
            log_event(cur, "error", "", 0, str(e))
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass

def run_scheduler():
    print("BIS DPL Scheduler started. Interval: 4 hours.")
    while True:
        run_once()
        print(f"Next check in 4 hours...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_scheduler()