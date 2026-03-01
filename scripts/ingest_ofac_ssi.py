import requests
import psycopg2
import os
import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

SSI_URL = "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/nonsdn.xml"

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "mic"),
        user=os.getenv("DB_USER", "mic_app"),
        password=os.getenv("DB_PASSWORD")
    )

def ingest_ssi():
    print(f"[{datetime.now(timezone.utc)}] Fetching OFAC SSI list...")
    response = requests.get(SSI_URL, timeout=120)
    raw_text = response.text
    content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    print(f"Downloaded {len(raw_text)} bytes | Hash: {content_hash[:16]}...")
    root = ET.fromstring(raw_text)
    entries = root.findall(".//{*}nonSdnEntity")
    print(f"Found {len(entries)} SSI entries")
    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    for entry in entries:
        def get(tag):
            el = entry.find(f"{{*}}{tag}")
            return el.text.strip() if el is not None and el.text else ""
        uid = get("id")
        last_name = get("lastName")
        first_name = get("firstName")
        entity_type = get("nonSdnType")
        programs = [p.text.strip() for p in entry.findall(".//{*}program") if p.text]
        cur.execute("""
            INSERT INTO ofac_ssi (uid, last_name, first_name, entity_type, programs, raw, ingested_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO UPDATE SET
                last_name = EXCLUDED.last_name,
                first_name = EXCLUDED.first_name,
                entity_type = EXCLUDED.entity_type,
                programs = EXCLUDED.programs,
                raw = EXCLUDED.raw,
                ingested_at = EXCLUDED.ingested_at
        """, (uid, last_name, first_name, entity_type, programs, json.dumps({
                "uid": uid,
                "lastName": last_name,
                "firstName": first_name,
                "nonSdnType": entity_type,
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
            }), datetime.now(timezone.utc)))
        inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Inserted/updated: {inserted} entries")

if __name__ == "__main__":
    ingest_ssi()