"""Entry/exit workflow and access decisions.

The database enforces invariants (one open visit per plate, consistent status, same-site
gates). This module owns the WORKFLOW: it runs in one transaction and first takes a
per-(site, plate) advisory lock, so two cameras reporting the same plate at the same moment
are processed one after the other instead of racing.
"""
import os
from typing import Optional

DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "30"))

_EXIT_REASON = {"resident": "resident", "staff": "staff", "visitor": "valid_pass"}


class GateNotFound(LookupError):
    pass


def _alert(conn, site_id, plate, alert_type, visit_id=None):
    conn.execute(
        "INSERT INTO alerts (site_id, plate, type, visit_id) VALUES (%s, %s, %s, %s)",
        (site_id, plate, alert_type, visit_id),
    )


def _log(conn, site_id, gate_id, plate, direction, decision, reason, confidence, visit_id, captured_at):
    conn.execute(
        """INSERT INTO access_logs
           (site_id, gate_id, plate, direction, decision, reason, confidence, visit_id, captured_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (site_id, gate_id, plate, direction, decision, reason, confidence, visit_id, captured_at),
    )


def _open_visit(conn, site_id, plate):
    return conn.execute(
        "SELECT * FROM visits WHERE site_id = %s AND plate = %s AND status = 'open' FOR UPDATE",
        (site_id, plate),
    ).fetchone()


def _entry_access(conn, site_id, plate, at):
    """Decide whether this plate may enter. Returns (allowed, access_category, reason, alert_type)."""
    vehicle = conn.execute(
        "SELECT role FROM vehicles WHERE site_id = %s AND plate = %s", (site_id, plate)
    ).fetchone()
    if vehicle:
        if vehicle["role"] == "blacklisted":
            return False, None, "blacklisted", "blacklisted"
        return True, vehicle["role"], vehicle["role"], None

    passes = conn.execute(
        "SELECT status, valid_from, valid_until FROM visitor_passes WHERE site_id = %s AND plate = %s",
        (site_id, plate),
    ).fetchall()
    if any(p["status"] == "active" and p["valid_from"] <= at <= p["valid_until"] for p in passes):
        return True, "visitor", "valid_pass", None
    if any(p["status"] == "active" for p in passes):
        return False, None, "expired_pass", "unknown_plate"   # pass exists, wrong time window
    if passes:
        return False, None, "no_pass", "unknown_plate"        # only revoked passes
    return False, None, "unknown_plate", "unknown_plate"


def process_detection(conn, site_id, gate_id, plate, confidence, captured_at,
                      image: Optional[str] = None, debounce: Optional[float] = None) -> dict:
    """Process one plate read. `plate` must already be normalized."""
    debounce = DEBOUNCE_SECONDS if debounce is None else debounce

    with conn.transaction():
        gate = conn.execute(
            "SELECT direction FROM gates WHERE id = %s AND site_id = %s", (gate_id, site_id)
        ).fetchone()
        if gate is None:
            raise GateNotFound("gate does not exist for this site")

        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{site_id}:{plate}",)
        )

        # Debounce: same plate at the same gate within N seconds is the same vehicle event.
        prior = conn.execute(
            """SELECT decision, reason, direction, visit_id FROM access_logs
               WHERE site_id = %s AND gate_id = %s AND plate = %s
                 AND captured_at BETWEEN %s::timestamptz - make_interval(secs => %s)
                                     AND %s::timestamptz + make_interval(secs => %s)
               ORDER BY captured_at DESC LIMIT 1""",
            (site_id, gate_id, plate, captured_at, debounce, captured_at, debounce),
        ).fetchone()
        if prior:
            return {"plate": plate, "duplicate": True, **prior, "alerts": []}

        open_v = _open_visit(conn, site_id, plate)
        direction = gate["direction"]
        if direction == "both":
            direction = "exit" if open_v else "entry"

        alerts, visit_id = [], None

        if direction == "entry":
            allowed, category, reason, alert_type = _entry_access(conn, site_id, plate, captured_at)
            if not allowed:
                decision = "deny"
                _alert(conn, site_id, plate, alert_type)
                alerts.append(alert_type)
            else:
                decision = "allow"
                if open_v:   # already inside but entering again: previous exit was never seen
                    conn.execute("UPDATE visits SET status = 'auto_closed' WHERE id = %s", (open_v["id"],))
                    _alert(conn, site_id, plate, "double_entry", open_v["id"])
                    alerts.append("double_entry")
                    decision, reason = "flag", "double_entry"
                visit_id = conn.execute(
                    """INSERT INTO visits (site_id, plate, access_category, entry_time, entry_gate_id, entry_image)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (site_id, plate, category, captured_at, gate_id, image),
                ).fetchone()["id"]
        else:  # exit
            if open_v:
                visit_id = open_v["id"]
                exit_time = max(captured_at, open_v["entry_time"])
                conn.execute(
                    """UPDATE visits SET exit_time = %s, exit_gate_id = %s, exit_image = %s, status = 'closed'
                       WHERE id = %s""",
                    (exit_time, gate_id, image, visit_id),
                )
                decision = "allow"
                reason = _EXIT_REASON.get(open_v["access_category"], "valid_pass")
                if open_v["access_category"] == "visitor":
                    p = conn.execute(
                        """SELECT valid_until FROM visitor_passes
                           WHERE site_id = %s AND plate = %s AND status = 'active' AND valid_from <= %s
                           ORDER BY valid_until DESC LIMIT 1""",
                        (site_id, plate, open_v["entry_time"]),
                    ).fetchone()
                    if p and exit_time > p["valid_until"]:
                        _alert(conn, site_id, plate, "overstay", visit_id)
                        alerts.append("overstay")
            else:   # let the car out, but flag it: there is no entry record
                decision, reason = "flag", "exit_without_entry"
                _alert(conn, site_id, plate, "exit_without_entry")
                alerts.append("exit_without_entry")

        _log(conn, site_id, gate_id, plate, direction, decision, reason, confidence, visit_id, captured_at)
        return {"plate": plate, "duplicate": False, "decision": decision, "reason": reason,
                "direction": direction, "visit_id": visit_id, "alerts": alerts}
