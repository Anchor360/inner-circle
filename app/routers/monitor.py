import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.infra.db import get_conn

router = APIRouter(prefix="/monitor", tags=["monitor"])


# ---------------------------
# Request / Response Models
# ---------------------------

class MonitorCreateRequest(BaseModel):
    entity_name: str
    entity_type: str = "individual"


class MonitorOut(BaseModel):
    monitor_id: str
    client_id: str
    entity_name: str
    entity_type: str
    status: str
    last_check_at: str | None
    last_check_result: dict | None
    last_status_change_at: str | None
    created_at: str


# ---------------------------
# POST /monitor
# ---------------------------

@router.post("", response_model=MonitorOut, status_code=201)
async def create_monitor(
    request: MonitorCreateRequest,
    x_api_key: str = Header(default="DEVKEY123")
):
    entity_name = request.entity_name.strip()
    if not entity_name:
        raise HTTPException(status_code=400, detail="entity_name is required")

    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        monitor_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        cur.execute("""
            INSERT INTO monitored_entities (
                id, client_id, entity_name, entity_type, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 'active', %s, %s)
        """, (monitor_id, client_id, entity_name, request.entity_type, now, now))

        conn.commit()

        return MonitorOut(
            monitor_id=monitor_id,
            client_id=client_id,
            entity_name=entity_name,
            entity_type=request.entity_type,
            status="active",
            last_check_at=None,
            last_check_result=None,
            last_status_change_at=None,
            created_at=now.isoformat(),
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# GET /monitor/{monitor_id}
# ---------------------------

@router.get("/{monitor_id}", response_model=MonitorOut)
async def get_monitor(monitor_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, client_id, entity_name, entity_type, status,
                   last_check_at, last_check_result, last_status_change_at, created_at
            FROM monitored_entities
            WHERE id = %s
        """, (monitor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Monitor not found")

        return MonitorOut(
            monitor_id=str(row[0]),
            client_id=row[1],
            entity_name=row[2],
            entity_type=row[3],
            status=row[4],
            last_check_at=row[5].isoformat() if row[5] else None,
            last_check_result=row[6] if isinstance(row[6], dict) else None,
            last_status_change_at=row[7].isoformat() if row[7] else None,
            created_at=row[8].isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# DELETE /monitor/{monitor_id}
# ---------------------------

@router.delete("/{monitor_id}", status_code=200)
async def delete_monitor(monitor_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE monitored_entities
            SET status = 'cancelled', updated_at = %s
            WHERE id = %s
        """, (datetime.now(timezone.utc), monitor_id))

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Monitor not found")

        conn.commit()
        return {"monitor_id": monitor_id, "status": "cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# GET /monitor (list all for client)
# ---------------------------

@router.get("", response_model=list[MonitorOut])
async def list_monitors(
    x_api_key: str = Header(default="DEVKEY123")
):
    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, client_id, entity_name, entity_type, status,
                   last_check_at, last_check_result, last_status_change_at, created_at
            FROM monitored_entities
            WHERE client_id = %s
            ORDER BY created_at DESC
        """, (client_id,))
        rows = cur.fetchall()

        return [
            MonitorOut(
                monitor_id=str(r[0]),
                client_id=r[1],
                entity_name=r[2],
                entity_type=r[3],
                status=r[4],
                last_check_at=r[5].isoformat() if r[5] else None,
                last_check_result=r[6] if isinstance(r[6], dict) else None,
                last_status_change_at=r[7].isoformat() if r[7] else None,
                created_at=r[8].isoformat(),
            )
            for r in rows
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()