import os
import json
import time
import requests
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

INTERVAL_SECONDS = 4 * 60 * 60  # 4 hours
API_BASE = os.getenv("API_BASE", "http://api:8000")
SYSTEM_API_KEY = os.getenv("SYSTEM_API_KEY", "DEVKEY999")


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "mic"),
        user=os.getenv("DB_USER", "mic_app"),
        password=os.getenv("DB_PASSWORD")
    )


def get_active_watchlist(cur):
    cur.execute("""
        SELECT id, entity_name, entity_type
        FROM watchlist
        WHERE is_active = TRUE
        ORDER BY added_at ASC
    """)
    return cur.fetchall()


def screen_entity(entity_name):
    """Run entity through all three verify endpoints. Return list of claim_ids."""
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": SYSTEM_API_KEY
    }
    payload = json.dumps({"entity_name": entity_name})
    endpoints = [
        "/verify/ofac",
        "/verify/bis",
        "/verify/ofac-consolidated",
    ]
    claim_ids = []
    for endpoint in endpoints:
        try:
            response = requests.post(
                f"{API_BASE}{endpoint}",
                data=payload,
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                claim_id = data.get("claim_id")
                if claim_id:
                    claim_ids.append(claim_id)
                    print(f"  [{endpoint}] claim_id: {claim_id}")
            else:
                print(f"  [{endpoint}] ERROR {response.status_code}: {response.text}")
        except Exception as e:
            print(f"  [{endpoint}] EXCEPTION: {e}")
    return claim_ids


def update_watchlist_entry(cur, watchlist_id, claim_ids):
    last_receipt_id = claim_ids[-1] if claim_ids else None
    cur.execute("""
        UPDATE watchlist
        SET last_checked_at = %s,
            last_receipt_id = %s
        WHERE id = %s
    """, (datetime.now(timezone.utc), last_receipt_id, watchlist_id))


def run_once():
    now = datetime.now(timezone.utc)
    print(f"[{now}] Watchlist scheduler starting...")

    try:
        conn = get_conn()
        cur = conn.cursor()

        entries = get_active_watchlist(cur)
        print(f"Active watchlist entries: {len(entries)}")

        if not entries:
            print("Nothing to screen. Sleeping.")
            cur.close()
            conn.close()
            return

        for row in entries:
            watchlist_id, entity_name, entity_type = row
            print(f"Screening: {entity_name} ({entity_type})")
            claim_ids = screen_entity(entity_name)
            update_watchlist_entry(cur, watchlist_id, claim_ids)
            print(f"  Updated watchlist entry {watchlist_id} with {len(claim_ids)} receipts")

        conn.commit()
        cur.close()
        conn.close()
        print(f"[{datetime.now(timezone.utc)}] Watchlist run complete.")

    except Exception as e:
        print(f"[ERROR] {e}")


def run_scheduler():
    print("Watchlist Scheduler started. Interval: 4 hours.")
    while True:
        run_once()
        print(f"Next run in 4 hours...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_scheduler()