import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.infra.db import get_conn

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


# ---------------------------
# Request / Response Models
# ---------------------------

class WatchlistCreateRequest(BaseModel):
    entity_name: str
    entity_type: str = "unknown"


class WatchlistOut(BaseModel):
    id: int
    client_id: str
    entity_name: str
    entity_type: str
    added_at: str
    last_checked_at: str | None
    last_receipt_id: str | None
    is_active: bool


# ---------------------------
# POST /watchlist
# ---------------------------

@router.post("", response_model=WatchlistOut, status_code=201)
async def add_to_watchlist(
    request: WatchlistCreateRequest,
    x_api_key: str = Header(default="DEVKEY123")
):
    entity_name = request.entity_name.strip()
    if not entity_name:
        raise HTTPException(status_code=400, detail="entity_name is required")

    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO watchlist (client_id, entity_name, entity_type)
            VALUES (%s, %s, %s)
            RETURNING id, client_id, entity_name, entity_type, added_at, last_checked_at, last_receipt_id, is_active
        """, (client_id, entity_name, request.entity_type))

        row = cur.fetchone()
        conn.commit()

        return WatchlistOut(
            id=row[0],
            client_id=row[1],
            entity_name=row[2],
            entity_type=row[3],
            added_at=row[4].isoformat(),
            last_checked_at=row[5].isoformat() if row[5] else None,
            last_receipt_id=row[6],
            is_active=row[7],
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# GET /watchlist
# ---------------------------

@router.get("", response_model=list[WatchlistOut])
async def list_watchlist(
    x_api_key: str = Header(default="DEVKEY123")
):
    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, client_id, entity_name, entity_type, added_at,
                   last_checked_at, last_receipt_id, is_active
            FROM watchlist
            WHERE client_id = %s AND is_active = TRUE
            ORDER BY added_at DESC
        """, (client_id,))
        rows = cur.fetchall()

        return [
            WatchlistOut(
                id=r[0],
                client_id=r[1],
                entity_name=r[2],
                entity_type=r[3],
                added_at=r[4].isoformat(),
                last_checked_at=r[5].isoformat() if r[5] else None,
                last_receipt_id=r[6],
                is_active=r[7],
            )
            for r in rows
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# DELETE /watchlist/{id}
# ---------------------------

@router.delete("/{watchlist_id}", status_code=200)
async def remove_from_watchlist(watchlist_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE watchlist
            SET is_active = FALSE
            WHERE id = %s
        """, (watchlist_id,))

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Watchlist entry not found")

        conn.commit()
        return {"id": watchlist_id, "status": "removed"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()