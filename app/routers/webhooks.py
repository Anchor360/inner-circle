import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.infra.db import get_conn

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------
# Request / Response Models
# ---------------------------

class WebhookCreateRequest(BaseModel):
    endpoint_url: str


class WebhookOut(BaseModel):
    id: int
    client_id: str
    endpoint_url: str
    is_active: bool
    created_at: str


# ---------------------------
# POST /webhooks
# ---------------------------

@router.post("", response_model=WebhookOut, status_code=201)
async def register_webhook(
    request: WebhookCreateRequest,
    x_api_key: str = Header(default="DEVKEY123")
):
    endpoint_url = request.endpoint_url.strip()
    if not endpoint_url:
        raise HTTPException(status_code=400, detail="endpoint_url is required")

    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO webhooks (client_id, endpoint_url)
            VALUES (%s, %s)
            RETURNING id, client_id, endpoint_url, is_active, created_at
        """, (client_id, endpoint_url))

        row = cur.fetchone()
        conn.commit()

        return WebhookOut(
            id=row[0],
            client_id=row[1],
            endpoint_url=row[2],
            is_active=row[3],
            created_at=row[4].isoformat(),
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# GET /webhooks
# ---------------------------

@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    x_api_key: str = Header(default="DEVKEY123")
):
    client_id = x_api_key or "unknown"

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, client_id, endpoint_url, is_active, created_at
            FROM webhooks
            WHERE client_id = %s AND is_active = TRUE
            ORDER BY created_at DESC
        """, (client_id,))
        rows = cur.fetchall()

        return [
            WebhookOut(
                id=r[0],
                client_id=r[1],
                endpoint_url=r[2],
                is_active=r[3],
                created_at=r[4].isoformat(),
            )
            for r in rows
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ---------------------------
# DELETE /webhooks/{id}
# ---------------------------

@router.delete("/{webhook_id}", status_code=200)
async def remove_webhook(webhook_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE webhooks
            SET is_active = FALSE
            WHERE id = %s
        """, (webhook_id,))

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Webhook not found")

        conn.commit()
        return {"id": webhook_id, "status": "removed"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()