import hashlib
import json
import xml.etree.ElementTree as ET
import io
import csv
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from rapidfuzz import fuzz

from app.infra.db import get_conn

router = APIRouter(prefix="/replay", tags=["replay"])


# ---------------------------
# GET /replay/{receipt_id}
# ---------------------------

@router.get("/{receipt_id}")
async def replay_receipt(receipt_id: str):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Step 1: Get the original event
        cur.execute("""
            SELECT event_id, event_type, aggregate_id, payload, created_at, event_hash
            FROM events
            WHERE aggregate_id = %s
            ORDER BY created_at ASC
            LIMIT 1
        """, (receipt_id,))
        event = cur.fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Receipt not found")

        event_id, event_type, aggregate_id, payload, verified_at, event_hash = event
        entity_name = payload.get("entity")
        data_version = payload.get("data_version")

        if not data_version:
            raise HTTPException(status_code=400, detail="Receipt has no data version — cannot replay")

        version_id = data_version.get("version_id")
        original_hash = data_version.get("content_hash")
        source = data_version.get("source")

        if not version_id:
            raise HTTPException(status_code=400, detail="Receipt has no version_id — cannot replay")

        # Step 2: Get the raw snapshot for that version
        cur.execute("""
            SELECT raw_bytes, content_hash
            FROM ingestion_snapshots
            WHERE version_id = %s
        """, (version_id,))
        snapshot = cur.fetchone()

        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"No raw snapshot found for version_id {version_id}. Snapshots are stored from ingestion cycles after this feature was added."
            )

        raw_bytes, snapshot_hash = snapshot

        # Step 3: Verify snapshot integrity
        computed_hash = hashlib.sha256(raw_bytes.encode()).hexdigest()
        hash_verified = computed_hash == original_hash

        # Step 4: Re-run the screen against the snapshot
        replay_hits = []
        FUZZY_THRESHOLD = 85

        if source in ("ofac_sdn", "ofac_consolidated"):
            try:
                root = ET.fromstring(raw_bytes)
                entries = root.findall(".//{*}sdnEntry")
                for entry in entries:
                    def get(tag):
                        el = entry.find(f"{{*}}{tag}")
                        return el.text.strip() if el is not None and el.text else ""
                    full_name = f"{get('firstName')} {get('lastName')}".strip()
                    score = max(
                        fuzz.token_sort_ratio(entity_name.upper(), full_name.upper()),
                        fuzz.partial_ratio(entity_name.upper(), full_name.upper()),
                    )
                    if score >= FUZZY_THRESHOLD:
                        replay_hits.append({
                            "name": full_name,
                            "match_score": round(score / 100, 2),
                        })
            except Exception as e:
                replay_hits = [{"error": f"Parse error: {str(e)}"}]

        elif source == "bis_dpl":
            try:
                reader = csv.DictReader(io.StringIO(raw_bytes))
                for row in reader:
                    name = row.get("Name", "").strip()
                    if not name:
                        continue
                    score = max(
                        fuzz.token_sort_ratio(entity_name.upper(), name.upper()),
                        fuzz.partial_ratio(entity_name.upper(), name.upper()),
                    )
                    if score >= FUZZY_THRESHOLD:
                        replay_hits.append({
                            "name": name,
                            "match_score": round(score / 100, 2),
                        })
            except Exception as e:
                replay_hits = [{"error": f"Parse error: {str(e)}"}]

        replay_match = len(replay_hits) > 0
        original_match = payload.get("match", False)
        result_consistent = replay_match == original_match

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Replay error: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return {
        "receipt_id": receipt_id,
        "entity": entity_name,
        "event_type": event_type,
        "verified_at": verified_at.isoformat(),
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "data_version": {
            "version_id": version_id,
            "content_hash": original_hash,
            "ingested_at": data_version.get("ingested_at"),
        },
        "integrity": {
            "hash_verified": hash_verified,
            "computed_hash": computed_hash,
            "original_hash": original_hash,
        },
        "original_result": {
            "match": original_match,
            "event_hash": event_hash,
        },
        "replay_result": {
            "match": replay_match,
            "hits": replay_hits[:5],
        },
        "result_consistent": result_consistent,
        "note": "Replay re-ran the original check against the raw snapshot stored at ingestion time. Hash verification confirms the snapshot is unmodified."
    }