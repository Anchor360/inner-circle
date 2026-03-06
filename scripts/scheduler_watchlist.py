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
        SELECT id, client_id, entity_name, entity_type, last_match_status
        FROM watchlist
        WHERE is_active = TRUE
        ORDER BY added_at ASC
    """)
    return cur.fetchall()


def get_client_webhooks(cur, client_id):
    cur.execute("""
        SELECT endpoint_url
        FROM webhooks
        WHERE client_id = %s AND is_active = TRUE
    """, (client_id,))
    return [row[0] for row in cur.fetchall()]


def screen_entity(entity_name):
    """Run entity through all three verify endpoints. Return claim_ids and whether any match was found."""
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": SYSTEM_API_KEY
    }
    payload = json.dumps({"entity_name": entity_name})
    endpoints = [
        ("/verify/ofac", "ofac_match"),
        ("/verify/bis", "bis_match"),
        ("/verify/ofac-consolidated", "ofac_consolidated_match"),
    ]
    claim_ids = []
    any_match = False

    for endpoint, match_key in endpoints:
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
                if data.get(match_key):
                    any_match = True
            else:
                print(f"  [{endpoint}] ERROR {response.status_code}: {response.text}")
        except Exception as e:
            print(f"  [{endpoint}] EXCEPTION: {e}")

    return claim_ids, any_match


def fire_webhooks(endpoints, entity_name, new_status, last_receipt_id, screened_at):
    """Fire alert to all registered webhook endpoints."""
    payload = {
        "event": "watchlist_alert",
        "entity_name": entity_name,
        "change": new_status,
        "receipt_id": last_receipt_id,
        "screened_at": screened_at.isoformat(),
    }
    headers = {"Content-Type": "application/json"}
    for url in endpoints:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            print(f"  Webhook fired to {url} — status {response.status_code}")
        except Exception as e:
            print(f"  Webhook failed for {url}: {e}")


def update_watchlist_entry(cur, watchlist_id, claim_ids, new_match_status):
    last_receipt_id = claim_ids[-1] if claim_ids else None
    cur.execute("""
        UPDATE watchlist
        SET last_checked_at = %s,
            last_receipt_id = %s,
            last_match_status = %s
        WHERE id = %s
    """, (datetime.now(timezone.utc), last_receipt_id, new_match_status, watchlist_id))


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
            watchlist_id, client_id, entity_name, entity_type, last_match_status = row
            print(f"Screening: {entity_name} ({entity_type})")

            claim_ids, any_match = screen_entity(entity_name)
            new_match_status = "match" if any_match else "clear"

            # Change detection
            status_changed = new_match_status != last_match_status
            if status_changed:
                print(f"  STATUS CHANGE: {last_match_status} → {new_match_status}")
                webhook_urls = get_client_webhooks(cur, client_id)
                if webhook_urls:
                    last_receipt_id = claim_ids[-1] if claim_ids else None
                    fire_webhooks(webhook_urls, entity_name, new_match_status, last_receipt_id, now)
                else:
                    print(f"  No webhooks registered for client {client_id}")
            else:
                print(f"  No status change ({new_match_status})")

            update_watchlist_entry(cur, watchlist_id, claim_ids, new_match_status)
            print(f"  Updated watchlist entry {watchlist_id}")

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