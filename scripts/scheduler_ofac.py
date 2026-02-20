import requests
import psycopg2
import os
import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

load_dotenv()

SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/sdn.xml"
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
        WHERE event_type = 'ofac_sdn_ingestion'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    return row[0] if row else None

def log_event(cur, status, content_hash, entries_updated, message):
    cur.execute("""
        INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, payload)
        VALUES (gen_random_uuid(), 'ofac_sdn_ingestion', 'system', 'ofac_sdn', 'scheduler', 'ofac_scheduler', %s)
    """, (
        json.dumps({
            "status": status,
            "content_hash": content_hash,
            "entries_updated": entries_updated,
            "message": message
        }),
    ))

def run_once():
    now = datetime.now(timezone.utc)
    print(f"[{now}] Starting OFAC SDN check...")

    try:
        response = requests.get(SDN_URL, timeout=120)
        raw_text = response.text
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        print(f"Downloaded {len(raw_text)} bytes | Hash: {content_hash[:16]}...")

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
        root = ET.fromstring(raw_text)
        entries = root.findall(".//{*}sdnEntry")
        print(f"Found {len(entries)} SDN entries")

        inserted = 0
        for entry in entries:
            def get(tag):
                el = entry.find(f"{{*}}{tag}")
                return el.text.strip() if el is not None and el.text else ""

            uid = get("uid")
            last_name = get("lastName")
            first_name = get("firstName")
            entity_type = get("sdnType")
            programs = [p.text.strip() for p in entry.findall(".//{*}program") if p.text]

            cur.execute("""
                INSERT INTO ofac_sdn (uid, last_name, first_name, entity_type, programs, raw, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (uid) DO UPDATE SET
                    last_name = EXCLUDED.last_name,
                    first_name = EXCLUDED.first_name,
                    entity_type = EXCLUDED.entity_type,
                    programs = EXCLUDED.programs,
                    raw = EXCLUDED.raw,
                    ingested_at = EXCLUDED.ingested_at
            """, (uid, last_name, first_name, entity_type, programs,
                  json.dumps({"uid": uid, "lastName": last_name, "firstName": first_name}),
                  datetime.now(timezone.utc)))
            inserted += 1

        log_event(cur, "updated", content_hash, inserted, f"Ingested {inserted} entries from updated SDN list.")
        conn.commit()
        cur.close()
        conn.close()
        print(f"Done. Inserted/updated: {inserted} entries")

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
    print("OFAC SDN Scheduler started. Interval: 4 hours.")
    while True:
        run_once()
        print(f"Next check in 4 hours...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_scheduler()
