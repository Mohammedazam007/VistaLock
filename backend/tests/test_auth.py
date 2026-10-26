from datetime import datetime, timedelta, timezone

from conftest import ENTRY, OTHER_SITE, PASSWORD, SITE

T0 = datetime(2026, 10, 22, 9, 0, 0, tzinfo=timezone.utc)
NOW = datetime.now(timezone.utc)


def pass_body(plate="MH12DE1433", **extra):
    return {"plate": plate, "visitor_name": "V", "valid_from": (NOW - timedelta(hours=1)).isoformat(),
            "valid_until": (NOW + timedelta(hours=3)).isoformat(), **extra}


# ---- login -------------------------------------------------------------------------------
def test_login_success_returns_token_and_user(client):
    r = client.post("/auth/login", json={"email": "Admin@Test.io ", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin" and body["user"]["timezone"] == "Asia/Kolkata"
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "admin@test.io"


def test_login_failures_do_not_reveal_which_part_was_wrong(client):
    wrong_pw = client.post("/auth/login", json={"email": "admin@test.io", "password": "nope"})
    no_user = client.post("/auth/login", json={"email": "ghost@test.io", "password": PASSWORD})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


# ---- authentication ---------------------------------------------------------------------
def test_dashboard_endpoints_need_a_token(anon, client):
    assert anon.get(f"/sites/{SITE}/inside").status_code == 401
    bad = client.get(f"/sites/{SITE}/inside", headers={"Authorization": "Bearer not.a.token"})
    assert bad.status_code == 401


def test_detections_need_the_api_key_and_a_user_token_is_not_enough(anon, admin, cv):
    body = {"site_id": SITE, "gate_id": ENTRY, "plate": "TS09AB1234", "captured_at": T0.isoformat()}
    assert anon.post("/detections", json=body).status_code == 401
    assert admin.post("/detections", json=body).status_code == 401
    wrong = cv.c.post("/detections", json=body, headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401
    assert cv.post("/detections", json=body).status_code == 200


# ---- authorization: site isolation and roles ----------------------------------------------
def test_other_sites_admin_cannot_read_this_site(other_admin):
    assert other_admin.get(f"/sites/{SITE}/inside").status_code == 403
    assert other_admin.get(f"/sites/{SITE}/vehicles").status_code == 403
    assert other_admin.post(f"/sites/{SITE}/passes", json=pass_body()).status_code == 403
    assert other_admin.get(f"/sites/{OTHER_SITE}/inside").status_code == 200


def test_security_can_read_but_only_admin_can_add_vehicles(guard, admin):
    assert guard.get(f"/sites/{SITE}/vehicles").status_code == 200
    body = {"plate": "KA05ZZ0001", "role": "resident", "owner_name": "New"}
    assert guard.post(f"/sites/{SITE}/vehicles", json=body).status_code == 403
    assert admin.post(f"/sites/{SITE}/vehicles", json=body).status_code == 201
    assert admin.post(f"/sites/{SITE}/vehicles", json=body).status_code == 409   # duplicate


def test_resident_is_limited_to_own_unit_passes(resident, guard):
    assert resident.get(f"/sites/{SITE}/inside").status_code == 403
    assert resident.get(f"/sites/{SITE}/alerts").status_code == 403

    # the resident tries to invite as another unit: the server overrides it
    mine = resident.post(f"/sites/{SITE}/passes", json=pass_body("MH12DE1433", host_unit="Z-999", host_name="Fake"))
    assert mine.status_code == 201
    assert (mine.json()["host_unit"], mine.json()["host_name"]) == ("A-101", "Ravi Kumar")

    # a guard issues a pass for another unit
    other = guard.post(f"/sites/{SITE}/passes", json=pass_body("KL07AA0001", host_unit="B-202"))
    assert other.status_code == 201

    listed = resident.get(f"/sites/{SITE}/passes").json()
    assert [p["plate"] for p in listed] == ["MH12DE1433"]          # only own unit
    assert len(guard.get(f"/sites/{SITE}/passes").json()) == 2     # staff see all

    assert resident.post(f"/sites/{SITE}/passes/{other.json()['id']}/revoke").status_code == 404
    assert resident.post(f"/sites/{SITE}/passes/{mine.json()['id']}/revoke").status_code == 200
    assert resident.get(f"/sites/{SITE}/passes").json()[0]["state"] == "revoked"


def test_alert_resolve_is_site_scoped(admin, cv, other_admin):
    cv.post("/detections", json={"site_id": SITE, "gate_id": ENTRY, "plate": "KA01A1234",
                                 "captured_at": T0.isoformat()})
    alert = admin.get(f"/sites/{SITE}/alerts").json()[0]
    assert other_admin.post(f"/sites/{OTHER_SITE}/alerts/{alert['id']}/resolve").status_code == 404
    assert other_admin.post(f"/sites/{SITE}/alerts/{alert['id']}/resolve").status_code == 403
    assert admin.post(f"/sites/{SITE}/alerts/{alert['id']}/resolve").status_code == 200
    assert admin.get(f"/sites/{SITE}/alerts").json() == []
    assert len(admin.get(f"/sites/{SITE}/alerts", params={"resolved": True}).json()) == 1


# ---- analytics / summary -------------------------------------------------------------------
def test_summary_and_hourly_analytics(admin, cv):
    now = datetime.now(timezone.utc)
    cv.post("/detections", json={"site_id": SITE, "gate_id": ENTRY, "plate": "TS09AB1234", "captured_at": now.isoformat()})
    cv.post("/detections", json={"site_id": SITE, "gate_id": ENTRY, "plate": "KA01A1234", "captured_at": now.isoformat()})

    s = admin.get(f"/sites/{SITE}/summary").json()
    assert (s["inside"], s["open_alerts"], s["denied_today"]) == (1, 1, 1)

    h = admin.get(f"/sites/{SITE}/analytics/hourly").json()
    assert len(h["hours"]) == 24 and sum(x["entries"] for x in h["hours"]) == 1
