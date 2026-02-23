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

CONSOLIDATED_URL = "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/consolidated.xml"
HEADERS = {"User-Agent": "Mozilla/5.0"}
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
        WHERE event_type = 'ofac_consolidated_ingestion'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    return row[0] if row else None

def record_version(cur, content_hash, entry_count):
    cur.execute("""
        INSERT INTO ingestion_versions (source, content_hash, entry_count)
        VALUES ('ofac_consolidated', %s, %s)
        RETURNING version_id
    """, (content_hash, entry_count))
    return cur.fetchone()[0]

def get_latest_event_hash(cur):
    cur.execute("""
        SELECT event_hash FROM events
        WHERE event_hash IS NOT NULL
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    return row[0] if row else None

def compute_event_hash(event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, payload, created_at, previous_hash):
    import json, hashlib
    canonical = json.dumps({
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "payload": payload,
        "created_at": created_at,
        "previous_hash": previous_hash,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def log_event(cur, status, content_hash, entries_updated, message):
    import uuid, json
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": status,
        "content_hash": content_hash,
        "entries_updated": entries_updated,
        "message": message
    }
    previous_hash = get_latest_event_hash(cur)
    event_hash = compute_event_hash(
        event_id=event_id,
        event_type="ofac_consolidated_ingestion",
        aggregate_type="system",
        aggregate_id="ofac_consolidated",
        actor_type="scheduler",
        actor_id="ofac_consolidated_scheduler",
        payload=payload,
        created_at=now,
        previous_hash=previous_hash,
    )
    cur.execute("""
        INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, payload, event_hash, previous_hash)
        VALUES (%s, 'ofac_consolidated_ingestion', 'system', 'ofac_consolidated', 'scheduler', 'ofac_consolidated_scheduler', %s, %s, %s)
    """, (event_id, json.dumps(payload), event_hash, previous_hash))

def run_once():
    now = datetime.now(timezone.utc)
    print(f"[{now}] Starting OFAC Consolidated check...")

    try:
        response = requests.get(CONSOLIDATED_URL, headers=HEADERS, timeout=120)
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
        print(f"Found {len(entries)} Consolidated entries")

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
                INSERT INTO ofac_consolidated (uid, last_name, first_name, entity_type, programs, raw, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (uid) DO UPDATE SET
                    last_name = EXCLUDED.last_name,
                    first_name = EXCLUDED.first_name,
                    entity_type = EXCLUDED.entity_type,
                    programs = EXCLUDED.programs,
                    raw = EXCLUDED.raw,
                    ingested_at = EXCLUDED.ingested_at
            """, (uid, last_name, first_name, entity_type, programs,
                  json.dumps({
                "uid": uid,
                "lastName": last_name,
                "firstName": first_name,
                "sdnType": entity_type,
                "programs": programs,
                "aliases": [a.text.strip() for a in entry.findall(".//{*}aka") if a.text],
                "addresses": [
                    {
                        "address": el.findtext("{*}address1") or "",
                        "city": el.findtext("{*}city") or "",
                        "country": el.findtext("{*}country") or "",
                    }
                    for el in entry.findall(".//{*}address")
                ],
                "ids": [
                    {
                        "idType": el.findtext("{*}idType") or "",
                        "idNumber": el.findtext("{*}idNumber") or "",
                    }
                    for el in entry.findall(".//{*}id")
                ],
                "nationalities": [n.text.strip() for n in entry.findall(".//{*}nationality") if n.text],
                "dateOfBirth": entry.findtext(".//{*}dateOfBirth") or "",
                "placeOfBirth": entry.findtext(".//{*}placeOfBirth") or "",
            }),
                  datetime.now(timezone.utc)))
            inserted += 1

        version_id = record_version(cur, content_hash, inserted)
        log_event(cur, "updated", content_hash, inserted, f"Ingested {inserted} entries from updated Consolidated list. Version ID: {version_id}")
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
    print("OFAC Consolidated Scheduler started. Interval: 4 hours.")
    while True:
        run_once()
        print(f"Next check in 4 hours...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_scheduler()