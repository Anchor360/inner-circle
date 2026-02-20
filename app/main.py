from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
import psycopg2
import json
import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import Request
from fastapi.responses import JSONResponse
import uuid
from fastapi.exceptions import RequestValidationError
import hashlib
import httpx
from fastapi import Header, Depends
from typing import Optional
import time
import logging
from app.infra.redis_client import get_redis_client

app = FastAPI(title="MIC POC", version="0.2")
# ---------------------------
# Structured Logging (A3)
# ---------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mic")

# ---------------------------
# API Key Auth (A2 strict)
# ---------------------------

def load_api_keys() -> dict[str, tuple[str, str]]:
    """
    MIC_API_KEYS format (comma-separated):
      key1:actor_type:actor_id,key2:actor_type:actor_id

    Example:
      MIC_API_KEYS="DEVKEY123:client:acme,DEVKEY999:system:api"
    """
    raw = os.getenv("MIC_API_KEYS", "").strip()
    mapping: dict[str, tuple[str, str]] = {}

    if not raw:
        return mapping

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        fields = p.split(":")
        if len(fields) != 3:
            raise RuntimeError("MIC_API_KEYS entries must be key:actor_type:actor_id")
        key, actor_type, actor_id = fields[0].strip(), fields[1].strip(), fields[2].strip()
        if not key or not actor_type or not actor_id:
            raise RuntimeError("MIC_API_KEYS entries must not be empty")
        mapping[key] = (actor_type, actor_id)

    return mapping

API_KEY_MAP = load_api_keys()

EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    request.state.trace_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response

@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Only enforce on write operations
    if request.method.upper() == "POST" and request.url.path not in EXEMPT_PATHS:
        api_key = request.headers.get("X-Api-Key")
        
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "type": "about:blank",
                    "title": "Request Error",
                    "status": 401,
                    "detail": "X-Api-Key header is required",
                    "instance": str(request.url.path),
                    "trace_id": getattr(request.state, "trace_id", None),
                },
            )

        actor = API_KEY_MAP.get(api_key)

        if not actor:
            return JSONResponse(
                status_code=401,
                content={
                    "type": "about:blank",
                    "title": "Request Error",
                    "status": 401,
                    "detail": "Invalid API key",
                    "instance": str(request.url.path),
                    "trace_id": getattr(request.state, "trace_id", None),
                },
            )

        request.state.actor_type, request.state.actor_id = actor

    return await call_next(request)

@app.middleware("http")
async def rate_limit_post_per_actor(request: Request, call_next):
    # Only enforce on write operations
    if request.method.upper() == "POST" and request.url.path not in EXEMPT_PATHS:
        actor_id = getattr(request.state, "actor_id", None)

        # If for some reason actor_id isn't set, we fail-open.
        if not actor_id:
            return await call_next(request)

        limit = int(os.getenv("RATE_LIMIT_POSTS_PER_MINUTE", "60"))

        # Redis client (fail-open if unavailable)
        r = get_redis_client()
        if r is None:
            # log a warning with context, but allow request
            logger.warning(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "trace_id": getattr(request.state, "trace_id", None),
                        "event": "rate_limit_unavailable",
                        "method": request.method,
                        "path": request.url.path,
                        "actor_id": actor_id,
                    }
                )
            )
            return await call_next(request)

        # Fixed 60-second window bucket (per-minute)
        now = int(time.time())
        bucket = now // 60
        key = f"rl:post:{actor_id}:{bucket}"

        try:
            # Increment and set expiry
            count = r.incr(key)
            if count == 1:
                r.expire(key, 60)

            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "about:blank",
                        "title": "Request Error",
                        "status": 429,
                        "detail": "Rate limit exceeded",
                        "instance": str(request.url.path),
                        "trace_id": getattr(request.state, "trace_id", None),
                    },
                    headers={"Retry-After": "60"},
                )

        except Exception:
            # Fail-open on Redis errors (but warn)
            logger.warning(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "trace_id": getattr(request.state, "trace_id", None),
                        "event": "rate_limit_error",
                        "method": request.method,
                        "path": request.url.path,
                        "actor_id": actor_id,
                    }
                )
            )

        return await call_next(request)

    return await call_next(request)

@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()

    response = await call_next(request)

    duration_ms = round((time.time() - start) * 1000, 2)

    log_record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": getattr(request.state, "trace_id", None),
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "latency_ms": duration_ms,
        "actor_type": getattr(request.state, "actor_type", None),
        "actor_id": getattr(request.state, "actor_id", None),
    }

    logger.info(json.dumps(log_record))

    return response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": "Request Error",
            "status": exc.status_code,
            "detail": exc.detail if isinstance(exc.detail, str) else "Request error",
            "instance": str(request.url.path),
            "trace_id": trace_id,
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = getattr(request.state, "trace_id", None)

    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "detail": "Request body validation failed",
            "instance": str(request.url.path),
            "trace_id": trace_id,
            "errors": exc.errors(),
        },
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Unexpected server error",
            "instance": str(request.url.path),
            "trace_id": trace_id,
        },
    )

# ---------------------------
# Database
# ---------------------------

def get_conn():
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    dbname = os.getenv("DB_NAME", "mic")
    user = os.getenv("DB_USER", "mic")
    password = os.getenv("DB_PASSWORD", "micpass")

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )

def emit_event(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    actor_type: str,
    actor_id: str,
    payload: dict,
    correlation_id: str | None = None,
) -> str:
    # ---- Strict ledger discipline enforcement ----

    # Enforce schema_version presence and type
    if "schema_version" not in payload:
        raise HTTPException(status_code=400, detail="payload must include schema_version")

    if not isinstance(payload["schema_version"], int) or payload["schema_version"] < 1:
        raise HTTPException(status_code=400, detail="schema_version must be int >= 1")

    # Enforce event_type format: aggregate.action
    if "." not in event_type:
        raise HTTPException(status_code=400, detail="event_type must follow aggregate.action format")

    namespace = event_type.split(".")[0]

    # Enforce namespace match
    if namespace != aggregate_type:
        raise HTTPException(status_code=400, detail="event_type namespace must match aggregate_type")

    # Generate server-side event_id
    event_id = str(uuid.uuid4())

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO events (
            event_id,
            event_type,
            aggregate_type,
            aggregate_id,
            actor_type,
            actor_id,
            correlation_id,
            payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            event_id,
            event_type,
            aggregate_type,
            aggregate_id,
            actor_type,
            actor_id,
            correlation_id,
            json.dumps(payload),
        ),
    )

    conn.commit()
    cur.close()
    conn.close()

    return event_id

def require_idempotency(
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    return idempotency_key

def get_actor(request: Request):
    # Industry standard: actor identity must come from auth (server-derived),
    # not from caller-supplied headers.
    actor_type = getattr(request.state, "actor_type", None)
    actor_id = getattr(request.state, "actor_id", None)

    if not actor_type or not actor_id:
        # If we ever hit this on a POST, it means auth middleware didn't set identity.
        raise HTTPException(status_code=401, detail="Unauthorized")

    return actor_type, actor_id

def compute_request_hash(payload: dict) -> str:
    # Deterministic JSON serialization: stable key order, no whitespace variance
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def get_idempotency_record(actor_type: str, actor_id: str, idempotency_key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT request_hash, event_id, aggregate_type, aggregate_id, response_created_at
        FROM idempotency_keys
        WHERE actor_type=%s AND actor_id=%s AND idempotency_key=%s
        """,
        (actor_type, actor_id, idempotency_key),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def store_idempotency_record(
    actor_type: str,
    actor_id: str,
    idempotency_key: str,
    request_hash: str,
    event_id: str,
    aggregate_type: str,
    aggregate_id: str,
    response_created_at: datetime,
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO idempotency_keys (
            actor_type,
            actor_id,
            idempotency_key,
            request_hash,
            event_id,
            aggregate_type,
            aggregate_id,
            response_created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor_type,
            actor_id,
            idempotency_key,
            request_hash,
            event_id,
            aggregate_type,
            aggregate_id,
            response_created_at,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()

# ---------------------------
# Claims
# ---------------------------

class ClaimIn(BaseModel):
    content: str


class ClaimOut(BaseModel):
    claim_id: str
    created_at: datetime


@app.post("/claims", response_model=ClaimOut)
def create_claim(
    claim: ClaimIn,
    idempotency_key: str = Depends(require_idempotency),
    actor: tuple[str, str] = Depends(get_actor),
):
    actor_type, actor_id = actor

    claim_id = str(uuid4())
    created_at = datetime.now(tz=timezone.utc)
    event_id = str(uuid.uuid4())

    request_payload = {"content": claim.content}
    request_hash = compute_request_hash(request_payload)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # 1) Claim idempotency first (DB unique constraint acts as lock)
        cur.execute(
            """
            INSERT INTO idempotency_keys (
                actor_type,
                actor_id,
                idempotency_key,
                request_hash,
                response_body,
                status_code,
                created_at,
                event_id,
                aggregate_type,
                aggregate_id,
                response_created_at
            )
            VALUES (%s, %s, %s, %s, NULL, NULL, now(), %s, %s, %s, NULL)
            ON CONFLICT (actor_type, actor_id, idempotency_key) DO NOTHING
            """,
            (actor_type, actor_id, idempotency_key, request_hash, event_id, "claim", claim_id),
        )

        if cur.rowcount == 0:
            # Someone else already owns this key: replay their stored response (standard behavior)
            cur.execute(
                """
                SELECT request_hash, status_code, response_body, aggregate_id, response_created_at
                FROM idempotency_keys
                WHERE actor_type=%s AND actor_id=%s AND idempotency_key=%s
                """,
                (actor_type, actor_id, idempotency_key),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Idempotency record missing after conflict")

            existing_hash, status_code, response_body, existing_aggregate_id, existing_created_at = row

            if existing_hash != request_hash:
                # Standard: conflict on same key with different payload
                raise HTTPException(status_code=409, detail="Idempotency-Key reuse with different payload")

            # If winner hasn't finished yet, client should retry
            if status_code is None or response_body is None:
                raise HTTPException(status_code=409, detail="Idempotency request in progress; retry")

            return JSONResponse(status_code=int(status_code), content=response_body)

        # 2) We won: create claim row
        cur.execute(
            """
            INSERT INTO claims (claim_id, content, created_at)
            VALUES (%s, %s, %s)
            """,
            (claim_id, claim.content, created_at),
        )

        # 3) We won: create event row (use same event_id stored in idempotency row)
        cur.execute(
            """
            INSERT INTO events (
                event_id,
                event_type,
                aggregate_type,
                aggregate_id,
                actor_type,
                actor_id,
                correlation_id,
                payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                event_id,
                "claim.created",
                "claim",
                claim_id,
                actor_type,
                actor_id,
                None,
                json.dumps(
                    {
                        "schema_version": 1,
                        "content": claim.content,
                        "created_at": created_at.isoformat(),
                    }
                ),
            ),
        )

        # 4) Standard: store exact response for replay
        response_body = {
            "claim_id": claim_id,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
        }
        status_code = 200

        cur.execute(
            """
            UPDATE idempotency_keys
            SET
                response_body = %s::jsonb,
                status_code = %s,
                response_created_at = %s
            WHERE actor_type=%s AND actor_id=%s AND idempotency_key=%s
            """,
            (
                json.dumps(response_body),
                status_code,
                created_at,
                actor_type,
                actor_id,
                idempotency_key,
            ),
        )

        conn.commit()
        return ClaimOut(claim_id=claim_id, created_at=created_at)

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# ---------------------------
# Validations
# ---------------------------

class ValidationIn(BaseModel):
    claim_id: str
    source_id: str
    outcome: str          # supports | refutes | inconclusive
    confidence: float     # 0.0 – 1.0
    evidence_ref: str | None = None


class ValidationOut(BaseModel):
    validation_id: str
    created_at: datetime


@app.post("/validations", response_model=ValidationOut)
def create_validation(v: ValidationIn):
    validation_id = str(uuid4())
    created_at = datetime.now(tz=timezone.utc)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO validations (
            validation_id,
            claim_id,
            source_id,
            outcome,
            confidence,
            evidence_ref,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            validation_id,
            v.claim_id,
            v.source_id,
            v.outcome,
            v.confidence,
            v.evidence_ref,
            created_at,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()

    return ValidationOut(
        validation_id=validation_id,
        created_at=created_at,
    )


# ---------------------------
# Read Models
# ---------------------------

class ClaimRead(BaseModel):
    claim_id: str
    content: str
    created_at: datetime


class ValidationRead(BaseModel):
    validation_id: str
    source_id: str
    outcome: str
    confidence: float
    evidence_ref: str | None
    created_at: datetime


class ClaimValidationsOut(BaseModel):
    claim: ClaimRead
    validations: list[ValidationRead]


# ---------------------------
# Read-only Endpoint
# ---------------------------

@app.get("/claims/{claim_id}/validations", response_model=ClaimValidationsOut)
def get_claim_validations(claim_id: str):
    conn = get_conn()
    cur = conn.cursor()

    # Claim (404 if missing)
    cur.execute(
        """
        SELECT claim_id, content, created_at
        FROM claims
        WHERE claim_id = %s
        """,
        (claim_id,),
    )
    claim_row = cur.fetchone()
    if not claim_row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Claim not found")

    claim = ClaimRead(
        claim_id=claim_row[0],
        content=claim_row[1],
        created_at=claim_row[2],
    )

    # Validations (newest first)
    cur.execute(
        """
        SELECT
            validation_id,
            source_id,
            outcome,
            confidence,
            evidence_ref,
            created_at
        FROM validations
        WHERE claim_id = %s
        ORDER BY created_at DESC
        """,
        (claim_id,),
    )

    validations = [
        ValidationRead(
            validation_id=row[0],
            source_id=str(row[1]),
            outcome=row[2],
            confidence=row[3],
            evidence_ref=row[4],
            created_at=row[5],
        )
        for row in cur.fetchall()
    ]

    cur.close()
    conn.close()

    return ClaimValidationsOut(
        claim=claim,
        validations=validations,
    )

# ---------------------------
# Events (Read-only)
# ---------------------------

class EventOut(BaseModel):
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_type: str
    actor_id: str
    correlation_id: str | None
    created_at: datetime
    payload: dict


@app.get("/events/{aggregate_type}/{aggregate_id}", response_model=list[EventOut])
def get_events_by_aggregate(aggregate_type: str, aggregate_id: str, limit: int = 50):
    # Guardrails: deterministic + bounded
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            event_id,
            event_type,
            aggregate_type,
            aggregate_id,
            actor_type,
            actor_id,
            correlation_id,
            created_at,
            payload
        FROM events
        WHERE aggregate_type = %s AND aggregate_id = %s
        ORDER BY created_at ASC, event_id ASC
        LIMIT %s
        """,
        (aggregate_type, aggregate_id, limit),
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        EventOut(
            event_id=str(r[0]),
            event_type=r[1],
            aggregate_type=r[2],
            aggregate_id=r[3],
            actor_type=r[4],
            actor_id=r[5],
            correlation_id=str(r[6]) if r[6] is not None else None,
            created_at=r[7],
            payload=r[8] if isinstance(r[8], dict) else dict(r[8]),
        )
        for r in rows
    ]

# ---------------------------
# Verdicts
# ---------------------------

class VerdictOut(BaseModel):
    verdict_id: str
    claim_id: str
    status: str  # verified | disputed | indeterminate
    score: float
    validation_count_total: int
    validation_count_scored: int
    created_at: datetime

@app.post("/claims/{claim_id}/verdicts/compute", response_model=VerdictOut, status_code=201)
def compute_verdict(claim_id: str):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # Ensure claim exists
        cur.execute("SELECT 1 FROM claims WHERE claim_id = %s", (claim_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Claim not found")

        # Count total validations (all)
        cur.execute("SELECT COUNT(*) FROM validations WHERE claim_id = %s", (claim_id,))
        validation_count_total = int(cur.fetchone()[0])

        # Count scored validations (exclude unclassified sources)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM validations v
            JOIN sources s ON s.source_id = v.source_id
            WHERE v.claim_id = %s
              AND s.authority_tier <> 'unclassified'
            """,
            (claim_id,),
        )
        validation_count_scored = int(cur.fetchone()[0])

        # Fetch scored validations we will actually use for scoring (include IDs for snapshot)
        cur.execute(
            """
            SELECT v.validation_id, v.outcome, v.confidence
            FROM validations v
            JOIN sources s ON s.source_id = v.source_id
            WHERE v.claim_id = %s
              AND s.authority_tier <> 'unclassified'
            """,
            (claim_id,),
        )
        rows = cur.fetchall()

        validation_ids = []
        weights = []

        for validation_id, outcome, confidence in rows:
            validation_ids.append(str(validation_id))
            if outcome == "supports":
                weights.append((1.0, confidence))
            elif outcome == "refutes":
                weights.append((0.0, confidence))
            # outcomes like "disputes" don't contribute to the numeric score in this v0.2 model

        # Compute score + status
        if not weights:
            score = 0.5
            status = "insufficient_evidence"
        else:
            numerator = sum(val * w for val, w in weights)
            denominator = sum(w for _, w in weights)
            score = numerator / denominator if denominator > 0 else 0.5

            if score >= 0.67:
                status = "supported"
            elif score <= 0.33:
                status = "refuted"
            else:
                status = "disputed"

        verdict_id = str(uuid4())
        created_at = datetime.now(tz=timezone.utc)

        cur.execute(
            """
            INSERT INTO verdicts (
                verdict_id,
                claim_id,
                status,
                confidence,
                validation_ids,
                created_at,
                score,
                validation_count_total,
                validation_count_scored
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                verdict_id,
                claim_id,
                status,
                float(score),                 # confidence (legacy field)
                json.dumps(validation_ids),   # snapshot of the scored validation_ids used
                created_at,
                float(score),                 # score (new field)
                validation_count_total,
                validation_count_scored,
            ),
        )

        conn.commit()

        return VerdictOut(
            verdict_id=verdict_id,
            claim_id=claim_id,
            status=status,
            score=float(score),
            validation_count_total=validation_count_total,
            validation_count_scored=validation_count_scored,
            created_at=created_at,
        )

    finally:
        cur.close()
        conn.close()

@app.get("/claims/{claim_id}/verdicts/latest")
def get_latest_verdict(claim_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            verdict_id,
            claim_id,
            status,
            confidence,
            validation_ids,
            created_at
        FROM verdicts
        WHERE claim_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (claim_id,)
    )

    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NO_VERDICT",
                "epistemic_status": "unknown",
                "message": "No verdict exists for this claim yet.",
                "next_action": {
                    "method": "POST",
                    "path": f"/claims/{claim_id}/verdicts/compute"
                }
            }
        )

    verdict = {
        "verdict_id": row[0],
        "claim_id": row[1],
        "status": row[2],
        "confidence": row[3],
        "validation_ids": row[4],
        "created_at": row[5].isoformat()
    }

    cur.close()
    conn.close()

    return verdict


@app.get("/claims/{claim_id}/verdicts")
def list_verdicts(claim_id: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            verdict_id,
            claim_id,
            status,
            confidence,
            validation_ids,
            created_at,
            score,
            validation_count_total,
            validation_count_scored
        FROM verdicts
        WHERE claim_id = %s
        ORDER BY created_at DESC
        """,
        (claim_id,)
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NO_VERDICTS",
                "epistemic_status": "unknown",
                "message": "No verdicts exist for this claim yet.",
                "next_action": {
                    "method": "POST",
                    "path": f"/claims/{claim_id}/verdicts/compute"
                }
            }
        )

    verdicts = []
    for r in rows:
        verdicts.append(
            {
                "verdict_id": r[0],
                "claim_id": r[1],
                "status": r[2],
                "confidence": r[3],
                "validation_ids": r[4],
                "created_at": r[5].isoformat(),
                "score": float(r[6]) if r[6] is not None else None,
                "validation_count_total": int(r[7]) if r[7] is not None else None,
                "validation_count_scored": int(r[8]) if r[8] is not None else None,
            }
        )

    return {"claim_id": claim_id, "verdicts": verdicts}

# ---------------------------
# OFAC Sanctions Verification
# ---------------------------

class OFACVerifyRequest(BaseModel):
    entity_name: str

@app.post("/verify/ofac")
async def verify_ofac(request: OFACVerifyRequest):
    entity_name = request.entity_name.strip()
    if not entity_name:
        raise HTTPException(status_code=400, detail="entity_name is required")

    # Step 1: Check OFAC sanctions list (local database)
    ofac_match = False
    ofac_detail = ""
    try:
        sdn_conn = get_conn()
        sdn_cur = sdn_conn.cursor()
        sdn_cur.execute("""
            SELECT uid, last_name, first_name, entity_type, programs
            FROM ofac_sdn
            WHERE UPPER(last_name) LIKE %s
            OR UPPER(first_name || ' ' || last_name) LIKE %s
            OR UPPER(last_name || ' ' || first_name) LIKE %s
            LIMIT 5
        """, (
            f"%{entity_name.upper()}%",
            f"%{entity_name.upper()}%",
            f"%{entity_name.upper()}%"
        ))
        results = sdn_cur.fetchall()
        sdn_cur.close()
        sdn_conn.close()

        if results:
            ofac_match = True
            hit = results[0]
            ofac_detail = f"MATCH FOUND: {hit[2]} {hit[1]} | Type: {hit[3]} | Programs: {', '.join(hit[4] or [])}"
        else:
            ofac_detail = "No match found on OFAC SDN list"
    except Exception as e:
        ofac_detail = f"OFAC lookup error: {str(e)}"

    # Step 2: Write full audit trail to database
    conn = get_conn()
    cur = conn.cursor()
    try:
        claim_id = str(uuid.uuid4())
        validation_id = str(uuid.uuid4())
        verdict_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(entity_name.encode()).hexdigest()

        cur.execute("""
            INSERT INTO claims (claim_id, content, created_at)
            VALUES (%s, %s, %s)
        """, (claim_id, entity_name, now))

        cur.execute("""
            INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id, actor_type, actor_id, payload, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (event_id, "ofac_verification", "claim", claim_id, "system", "system", json.dumps({
            "entity": entity_name,
            "match": ofac_match,
            "detail": ofac_detail
        }), now))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return {
        "entity": entity_name,
        "ofac_match": ofac_match,
        "detail": ofac_detail,
        "claim_id": claim_id,
        "verified_at": now.isoformat(),
        "source": "OFAC SDN via trade.gov"
    }

@app.get("/health")
def health():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "healthy", "db": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database unreachable")
