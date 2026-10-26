import threading
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from app.decision import process_detection
from conftest import ENTRY, ENTRY2, EXIT, OTHER_GATE, OTHER_SITE, SITE, TEST_DB

T0 = datetime(2026, 10, 22, 9, 0, 0, tzinfo=timezone.utc)


def det(cv, plate, gate=ENTRY, at=T0, site=SITE):
    r = cv.post("/detections", json={"site_id": site, "gate_id": gate, "plate": plate,
                                         "confidence": 0.9, "captured_at": at.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def create_pass(admin, plate, start, end):
    r = admin.post(f"/sites/{SITE}/passes", json={"plate": plate, "visitor_name": "V", "host_name": "Ravi",
                                                   "valid_from": start.isoformat(), "valid_until": end.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()


def test_resident_entry_then_exit_records_times_and_duration(admin, cv):
    out = det(cv, "TS09AB1234")
    assert (out["decision"], out["reason"], out["direction"]) == ("allow", "resident", "entry")
    inside = admin.get(f"/sites/{SITE}/inside").json()
    assert [v["plate"] for v in inside] == ["TS09AB1234"]

    out = det(cv, "TS09AB1234", gate=EXIT, at=T0 + timedelta(hours=2, minutes=30))
    assert (out["decision"], out["direction"]) == ("allow", "exit")
    assert admin.get(f"/sites/{SITE}/inside").json() == []

    visit = admin.get(f"/sites/{SITE}/visits", params={"plate": "ts09 ab1234"}).json()[0]
    assert visit["status"] == "closed"
    assert visit["entry_time"].startswith("2026-10-22T09:00:00")
    assert visit["exit_time"].startswith("2026-10-22T11:30:00")
    assert visit["duration_seconds"] == 9000


def test_unknown_plate_denied_with_alert_and_no_visit(admin, cv):
    out = det(cv, "KA01A1234")
    assert (out["decision"], out["reason"]) == ("deny", "unknown_plate")
    assert admin.get(f"/sites/{SITE}/visits").json() == []
    assert [a["type"] for a in admin.get(f"/sites/{SITE}/alerts").json()] == ["unknown_plate"]


def test_blacklisted_denied(admin, cv):
    out = det(cv, "TS10EF9999")
    assert (out["decision"], out["reason"]) == ("deny", "blacklisted")
    assert admin.get(f"/sites/{SITE}/alerts").json()[0]["type"] == "blacklisted"


def test_visitor_pass_window(admin, cv):
    create_pass(admin, "MH12DE1433", T0 - timedelta(hours=1), T0 + timedelta(hours=3))
    ok = det(cv, "MH12DE1433", at=T0)
    assert (ok["decision"], ok["reason"]) == ("allow", "valid_pass")

    create_pass(admin, "KL07AA0001", T0 + timedelta(hours=5), T0 + timedelta(hours=8))
    early = det(cv, "KL07AA0001", at=T0)
    assert (early["decision"], early["reason"]) == ("deny", "expired_pass")


def test_revoked_pass_denied(admin, cv):
    p = create_pass(admin, "MH12DE1433", T0 - timedelta(hours=1), T0 + timedelta(hours=3))
    assert admin.post(f"/sites/{SITE}/passes/{p['id']}/revoke").status_code == 200
    out = det(cv, "MH12DE1433", at=T0)
    assert (out["decision"], out["reason"]) == ("deny", "no_pass")


def test_double_entry_flags_and_auto_closes_old_visit(admin, cv, db):
    det(cv, "TS09AB1234", at=T0)
    out = det(cv, "TS09AB1234", at=T0 + timedelta(minutes=10))
    assert (out["decision"], out["reason"]) == ("flag", "double_entry")
    statuses = [r["status"] for r in db.execute("SELECT status FROM visits ORDER BY entry_time").fetchall()]
    assert statuses == ["auto_closed", "open"]
    assert "double_entry" in [a["type"] for a in admin.get(f"/sites/{SITE}/alerts").json()]


def test_exit_without_entry_is_flagged_not_blocked(admin, cv):
    out = det(cv, "TS09AB1234", gate=EXIT)
    assert (out["decision"], out["reason"]) == ("flag", "exit_without_entry")
    assert admin.get(f"/sites/{SITE}/visits").json() == []
    assert admin.get(f"/sites/{SITE}/alerts").json()[0]["type"] == "exit_without_entry"


def test_debounce_ignores_repeat_reads_at_same_gate(admin, cv, db):
    det(cv, "TS09AB1234", at=T0)
    again = det(cv, "TS09AB1234", at=T0 + timedelta(seconds=5))
    assert again["duplicate"] is True
    assert db.execute("SELECT count(*) AS n FROM visits").fetchone()["n"] == 1
    assert db.execute("SELECT count(*) AS n FROM access_logs").fetchone()["n"] == 1


def test_visitor_overstay_alert_on_exit_and_overstay_endpoint(admin, cv):
    create_pass(admin, "MH12DE1433", T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    det(cv, "MH12DE1433", at=T0)
    out = det(cv, "MH12DE1433", gate=EXIT, at=T0 + timedelta(hours=3))
    assert out["alerts"] == ["overstay"]

    # still inside after the window (window ended long before "now")
    create_pass(admin, "KL07AA0001", T0 - timedelta(hours=1), T0 + timedelta(hours=1))
    det(cv, "KL07AA0001", at=T0)
    assert [o["plate"] for o in admin.get(f"/sites/{SITE}/overstays").json()] == ["KL07AA0001"]


def test_gate_from_another_site_is_rejected(admin, cv):
    r = cv.post("/detections", json={"site_id": SITE, "gate_id": OTHER_GATE, "plate": "TS09AB1234",
                                         "captured_at": T0.isoformat()})
    assert r.status_code == 404


def test_input_validation(admin, cv):
    base = {"site_id": SITE, "gate_id": ENTRY, "captured_at": T0.isoformat()}
    assert cv.post("/detections", json={**base, "plate": "ab"}).status_code == 422
    assert cv.post("/detections", json={**base, "plate": "TS09AB1234",
                                            "captured_at": "2026-10-22T09:00:00"}).status_code == 422  # no timezone
    assert det(cv, "ts 09-ab 1234")["plate"] == "TS09AB1234"


def test_concurrent_reads_of_same_plate_never_break_one_open_visit_rule(db):
    """Two cameras report the same plate at the same instant; the advisory lock serializes them."""
    errors = []

    def worker(gate, i):
        try:
            with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
                process_detection(conn, SITE, gate, "TS09AB1234", 0.9, T0 + timedelta(minutes=i * 5))
        except Exception as e:   # pragma: no cover
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(g, i)) for i in range(8) for g in (ENTRY, ENTRY2)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    assert db.execute("SELECT count(*) AS n FROM visits WHERE status = 'open'").fetchone()["n"] == 1
