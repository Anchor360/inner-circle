import os
import sys
import json
import uuid
import time
import logging
from datetime import datetime, timezone

import psycopg2
from rapidfuzz import fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------
# DB Connection
# ---------------------------

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "mic"),
        user=os.getenv("DB_USER", "mic_app"),
        password=os.getenv("DB_PASSWORD", "mic_app_pass"),
    )


# ---------------------------
# Screening Logic
# ---------------------------

FUZZY_THRESHOLD = 85

def screen_entity(entity_name: str) -> dict:
    results = {}

    conn = get_conn()
    cur = conn.cursor()

    try:
        # OFAC SDN
        cur.execute("""
            SELECT uid, last_name, first_name, entity_type, programs
            FROM ofac_sdn
            WHERE UPPER(last_name) LIKE %s
            OR UPPER(first_name || ' ' || last_name) LIKE %s
            LIMIT 200
        """, (f"%{entity_name.upper()[:4]}%", f"%{entity_name.upper()[:4]}%"))
        candidates = cur.fetchall()

        sdn_hits = []
        for row in candidates:
            full_name = f"{row[2] or ''} {row[1]}".strip()
            score = max(
                fuzz.token_sort_ratio(entity_name.upper(), full_name.upper()),
                fuzz.token_sort_ratio(entity_name.upper(), (row[1] or '').upper()),
                fuzz.partial_ratio(entity_name.upper(), full_name.upper()),
            )
            if score >= FUZZY_THRESHOLD:
                sdn_hits.append({"uid": row[0], "name": full_name, "score": round(score / 100, 2)})

        results["ofac_sdn"] = {
            "match": len(sdn_hits) > 0,
            "hit_count": len(sdn_hits),
            "top_hit": sdn_hits[0] if sdn_hits else None,
        }

        # BIS DPL
        cur.execute("""
            SELECT name, country, action
            FROM bis_dpl
            WHERE UPPER(name) LIKE %s
            LIMIT 200
        """, (f"%{entity_name.upper()[:4]}%",))
        candidates = cur.fetchall()

        bis_hits = []
        for row in candidates:
            score = max(
                fuzz.token_sort_ratio(entity_name.upper(), (row[0] or '').upper()),
                fuzz.partial_ratio(entity_name.upper(), (row[0] or '').upper()),
            )
            if score >= FUZZY_THRESHOLD:
                bis_hits.append({"name": row[0], "country": row[1], "score": round(score / 100, 2)})

        results["bis_dpl"] = {
            "match": len(bis_hits) > 0,
            "hit_count": len(bis_hits),
            "top_hit": bis_hits[0] if bis_hits else None,
        }

        # OFAC Consolidated
        cur.execute("""
            SELECT uid, last_name, first_name, entity_type, programs
            FROM ofac_consolidated
            WHERE UPPER(last_name) LIKE %s
            OR UPPER(first_name || ' ' || last_name) LIKE %s
            LIMIT 200
        """, (f"%{entity_name.upper()[:4]}%", f"%{entity_name.upper()[:4]}%"))
        candidates = cur.fetchall()

        con_hits = []
        for row in candidates:
            full_name = f"{row[2] or ''} {row[1]}".strip()
            score = max(
                fuzz.token_sort_ratio(entity_name.upper(), full_name.upper()),
                fuzz.token_sort_ratio(entity_name.upper(), (row[1] or '').upper()),
                fuzz.partial_ratio(entity_name.upper(), full_name.upper()),
            )
            if score >= FUZZY_THRESHOLD:
                con_hits.append({"uid": row[0], "name": full_name, "score": round(score / 100, 2)})

        results["ofac_consolidated"] = {
            "match": len(con_hits) > 0,
            "hit_count": len(con_hits),
            "top_hit": con_hits[0] if con_hits else None,
        }

    finally:
        cur.close()
        conn.close()

    results["any_match"] = any(r["match"] for r in results.values() if isinstance(r, dict))
    results["checked_at"] = datetime.now(timezone.utc).isoformat()

    return results


# ---------------------------
# Change Detection
# ---------------------------

def result_changed(previous: dict, current: dict) -> bool:
    if previous is None:
        return True
    for list_name in ["ofac_sdn", "bis_dpl", "ofac_consolidated"]:
        prev_match = previous.get(list_name, {}).get("match", False)
        curr_match = current.get(list_name, {}).get("match", False)
        if prev_match != curr_match:
            return True
    return False


# ---------------------------
# Main Loop
# ---------------------------

def run_monitor_cycle():
    logger.info("Starting monitor cycle")
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, entity_name, last_check_result
            FROM monitored_entities
            WHERE status = 'active'
        """)
        entities = cur.fetchall()
        logger.info(f"Found {len(entities)} active monitored entities")
    finally:
        cur.close()
        conn.close()

    for row in entities:
        monitor_id = str(row[0])
        entity_name = row[1]
        previous_result = row[2]

        logger.info(f"Checking: {entity_name}")

        try:
            current_result = screen_entity(entity_name)
            changed = result_changed(previous_result, current_result)

            conn = get_conn()
            cur = conn.cursor()
            try:
                now = datetime.now(timezone.utc)

                if changed:
                    cur.execute("""
                        UPDATE monitored_entities
                        SET last_check_at = %s,
                            last_check_result = %s,
                            last_status_change_at = %s,
                            updated_at = %s
                        WHERE id = %s
                    """, (now, json.dumps(current_result), now, now, monitor_id))

                    event_id = str(uuid.uuid4())
                    event_type = "status_changed" if previous_result is not None else "initial_check"
                    cur.execute("""
                        INSERT INTO monitor_events (
                            id, monitor_id, event_type, previous_result,
                            current_result, detected_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        event_id, monitor_id, event_type,
                        json.dumps(previous_result) if previous_result else None,
                        json.dumps(current_result),
                        now
                    ))
                    logger.info(f"Change detected for {entity_name} — event written")

                else:
                    cur.execute("""
                        UPDATE monitored_entities
                        SET last_check_at = %s,
                            last_check_result = %s,
                            updated_at = %s
                        WHERE id = %s
                    """, (now, json.dumps(current_result), now, monitor_id))
                    logger.info(f"No change for {entity_name}")

                conn.commit()

            finally:
                cur.close()
                conn.close()

        except Exception as e:
            logger.error(f"Error checking {entity_name}: {str(e)}")
            continue


# ---------------------------
# Entry Point
# ---------------------------

CHECK_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "3600"))

if __name__ == "__main__":
    logger.info(f"Monitor scheduler starting. Interval: {CHECK_INTERVAL_SECONDS}s")
    while True:
        try:
            run_monitor_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {str(e)}")
        logger.info(f"Sleeping {CHECK_INTERVAL_SECONDS}s until next cycle")
        time.sleep(CHECK_INTERVAL_SECONDS)