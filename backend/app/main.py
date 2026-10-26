from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg.errors
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .auth import (DUMMY_HASH, check_site, create_token, current_user, require_cv_key,
                   verify_password)
from .db import get_conn, pool
from .decision import GateNotFound, process_detection
from .models import DetectionIn, LoginIn, PassIn, VehicleIn, normalize_plate

STAFF = ("admin", "security")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(title="VistaLock API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health(conn=Depends(get_conn)):
    conn.execute("SELECT 1")
    return {"status": "ok"}


# ---- Auth ---------------------------------------------------------------------------------
def _public_user(u):
    return {"id": u["id"], "email": u["email"], "role": u["role"], "unit": u["unit"],
            "full_name": u["full_name"], "site_id": u["site_id"], "site_name": u["site_name"],
            "timezone": u["timezone"]}


@app.post("/auth/login")
def login(body: LoginIn, conn=Depends(get_conn)):
    row = conn.execute(
        """SELECT u.id, u.site_id, u.email, u.role, u.unit, u.full_name, u.password_hash,
                  s.name AS site_name, s.timezone
           FROM users u JOIN sites s ON s.id = u.site_id WHERE u.email = %s""",
        (body.email.lower().strip(),)).fetchone()
    ok = verify_password(body.password, row["password_hash"] if row else DUMMY_HASH)
    if not row or not ok:
        raise HTTPException(401, "invalid email or password")
    return {"access_token": create_token(row["id"]), "token_type": "bearer", "user": _public_user(row)}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return _public_user(user)


# ---- CV service -> backend (API key, not a user token) -----------------------------------
@app.post("/detections", dependencies=[Depends(require_cv_key)])
def post_detection(d: DetectionIn, conn=Depends(get_conn)):
    try:
        return process_detection(conn, d.site_id, d.gate_id, d.plate, d.confidence, d.captured_at, d.image)
    except GateNotFound as e:
        raise HTTPException(404, str(e))


# ---- Dashboard reads (admin / security) -----------------------------------------------------
@app.get("/sites/{site_id}/summary")
def summary(site_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, *STAFF)
    return conn.execute(
        """WITH s AS (SELECT timezone FROM sites WHERE id = %(site)s)
           SELECT
             (SELECT count(*)::int FROM visits WHERE site_id = %(site)s AND status = 'open') AS inside,
             (SELECT count(*)::int FROM alerts WHERE site_id = %(site)s AND NOT resolved) AS open_alerts,
             (SELECT count(*)::int FROM visits v, s WHERE v.site_id = %(site)s
                AND (v.entry_time AT TIME ZONE s.timezone)::date = (now() AT TIME ZONE s.timezone)::date) AS visits_today,
             (SELECT count(*)::int FROM access_logs a, s WHERE a.site_id = %(site)s AND a.decision = 'deny'
                AND (a.captured_at AT TIME ZONE s.timezone)::date = (now() AT TIME ZONE s.timezone)::date) AS denied_today""",
        {"site": site_id}).fetchone()


@app.get("/sites/{site_id}/inside")
def inside(site_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Vehicles currently inside (open visits)."""
    check_site(user, site_id, *STAFF)
    return conn.execute(
        """SELECT id, plate, access_category, entry_time,
                  EXTRACT(EPOCH FROM (now() - entry_time))::float AS inside_seconds
           FROM visits WHERE site_id = %s AND status = 'open' ORDER BY entry_time DESC""",
        (site_id,)).fetchall()


@app.get("/sites/{site_id}/visits")
def visits(site_id: UUID, plate: Optional[str] = None, date_from: Optional[datetime] = None,
           date_to: Optional[datetime] = None, limit: int = Query(100, ge=1, le=1000),
           user=Depends(current_user), conn=Depends(get_conn)):
    """Entry/exit log with dates and duration. Filter by plate and/or entry date range."""
    check_site(user, site_id, *STAFF)
    p = plate and normalize_plate(plate)
    return conn.execute(
        """SELECT id, plate, access_category, status, entry_time, exit_time,
                  EXTRACT(EPOCH FROM (exit_time - entry_time))::float AS duration_seconds
           FROM visits
           WHERE site_id = %s
             AND (%s::text IS NULL OR plate LIKE %s)
             AND (%s::timestamptz IS NULL OR entry_time >= %s)
             AND (%s::timestamptz IS NULL OR entry_time <= %s)
           ORDER BY entry_time DESC LIMIT %s""",
        (site_id, p, f"%{p}%" if p else None, date_from, date_from, date_to, date_to, limit)).fetchall()


@app.get("/sites/{site_id}/alerts")
def alerts(site_id: UUID, resolved: bool = False, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, *STAFF)
    return conn.execute(
        "SELECT * FROM alerts WHERE site_id = %s AND resolved = %s ORDER BY created_at DESC LIMIT 200",
        (site_id, resolved)).fetchall()


@app.post("/sites/{site_id}/alerts/{alert_id}/resolve")
def resolve_alert(site_id: UUID, alert_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, *STAFF)
    row = conn.execute("UPDATE alerts SET resolved = TRUE WHERE id = %s AND site_id = %s RETURNING id",
                       (alert_id, site_id)).fetchone()
    if row is None:
        raise HTTPException(404, "alert not found")
    return {"resolved": True}


@app.get("/sites/{site_id}/access-logs")
def access_logs(site_id: UUID, limit: int = Query(100, ge=1, le=1000),
                user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, *STAFF)
    return conn.execute(
        """SELECT id, gate_id, plate, direction, decision, reason, confidence, captured_at
           FROM access_logs WHERE site_id = %s ORDER BY captured_at DESC LIMIT %s""",
        (site_id, limit)).fetchall()


@app.get("/sites/{site_id}/overstays")
def overstays(site_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Visitors still inside after their pass window ended."""
    check_site(user, site_id, *STAFF)
    return conn.execute(
        """SELECT v.id AS visit_id, v.plate, v.entry_time, p.valid_until,
                  EXTRACT(EPOCH FROM (now() - p.valid_until))::float AS overdue_seconds
           FROM visits v
           JOIN LATERAL (SELECT valid_until FROM visitor_passes p
                         WHERE p.site_id = v.site_id AND p.plate = v.plate
                           AND p.status = 'active' AND p.valid_from <= v.entry_time
                         ORDER BY valid_until DESC LIMIT 1) p ON TRUE
           WHERE v.site_id = %s AND v.status = 'open' AND v.access_category = 'visitor'
             AND p.valid_until < now()
           ORDER BY overdue_seconds DESC""",
        (site_id,)).fetchall()


@app.get("/sites/{site_id}/analytics/hourly")
def hourly(site_id: UUID, days: int = Query(30, ge=1, le=365),
           user=Depends(current_user), conn=Depends(get_conn)):
    """Entries per hour of day (site timezone) over the last N days: the peak-hours chart."""
    check_site(user, site_id, *STAFF)
    rows = conn.execute(
        """SELECT EXTRACT(HOUR FROM v.entry_time AT TIME ZONE s.timezone)::int AS hour, count(*)::int AS entries
           FROM visits v JOIN sites s ON s.id = v.site_id
           WHERE v.site_id = %s AND v.entry_time >= now() - make_interval(days => %s)
           GROUP BY 1""", (site_id, days)).fetchall()
    by_hour = {r["hour"]: r["entries"] for r in rows}
    return {"days": days, "hours": [{"hour": h, "entries": by_hour.get(h, 0)} for h in range(24)]}


# ---- Registry (admin writes, staff reads) ---------------------------------------------------
@app.post("/sites/{site_id}/vehicles", status_code=201)
def add_vehicle(site_id: UUID, v: VehicleIn, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, "admin")
    try:
        return conn.execute(
            """INSERT INTO vehicles (site_id, plate, owner_name, role, unit)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (site_id, v.plate, v.owner_name, v.role, v.unit)).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "vehicle already registered for this site")


@app.get("/sites/{site_id}/vehicles")
def list_vehicles(site_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id, *STAFF)
    return conn.execute("SELECT * FROM vehicles WHERE site_id = %s ORDER BY plate", (site_id,)).fetchall()


# ---- Visitor passes (staff: any unit | resident: own unit only) -------------------------------
_PASS_SQL = """SELECT *, CASE WHEN status = 'revoked' THEN 'revoked'
                            WHEN now() < valid_from THEN 'upcoming'
                            WHEN now() > valid_until THEN 'expired'
                            ELSE 'active' END AS state
               FROM visitor_passes"""


@app.get("/sites/{site_id}/passes")
def list_passes(site_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id)
    if user["role"] == "resident":
        return conn.execute(_PASS_SQL + " WHERE site_id = %s AND host_unit = %s ORDER BY valid_from DESC LIMIT 200",
                            (site_id, user["unit"])).fetchall()
    return conn.execute(_PASS_SQL + " WHERE site_id = %s ORDER BY valid_from DESC LIMIT 200", (site_id,)).fetchall()


@app.post("/sites/{site_id}/passes", status_code=201)
def create_pass(site_id: UUID, p: PassIn, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id)
    host_name, host_unit = p.host_name, p.host_unit
    if user["role"] == "resident":      # residents can only invite for themselves; ignore what they sent
        host_name, host_unit = user["full_name"], user["unit"]
    return conn.execute(
        """INSERT INTO visitor_passes (site_id, plate, visitor_name, host_name, host_unit, valid_from, valid_until)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (site_id, p.plate, p.visitor_name, host_name, host_unit, p.valid_from, p.valid_until)).fetchone()


@app.post("/sites/{site_id}/passes/{pass_id}/revoke")
def revoke_pass(site_id: UUID, pass_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    check_site(user, site_id)
    sql = "UPDATE visitor_passes SET status = 'revoked' WHERE id = %s AND site_id = %s"
    params = [pass_id, site_id]
    if user["role"] == "resident":
        sql += " AND host_unit = %s"
        params.append(user["unit"])
    if conn.execute(sql + " RETURNING id", params).fetchone() is None:
        raise HTTPException(404, "pass not found")
    return {"revoked": True}
