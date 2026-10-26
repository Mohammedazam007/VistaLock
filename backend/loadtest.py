"""Simulate many gates hitting the API at once and report throughput and latency.

Each simulated gate is a thread that sends entry then exit for its own registered vehicles.
Run it on YOUR machine against your own setup and quote those numbers, not anyone else's.

    python loadtest.py --api-url http://localhost:8000 --gates 50 --events 20

Needs the seeded demo database (admin login + the seed site/gates).
"""
import argparse
import json
import statistics
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

SITE = "11111111-1111-1111-1111-111111111111"
ENTRY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
EXIT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def call(url, body=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def plate(gate, i):
    return f"TS{gate % 100:02d}{LETTERS[i % 24]}{LETTERS[(i // 24) % 24]}{1000 + gate:04d}"[:10]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-url", default="http://localhost:8000")
    ap.add_argument("--gates", type=int, default=20, help="concurrent simulated gates (threads)")
    ap.add_argument("--events", type=int, default=10, help="entry+exit cycles per gate")
    ap.add_argument("--api-key", default="dev-cv-key")
    ap.add_argument("--admin-email", default="admin@sunrise.test")
    ap.add_argument("--admin-password", default="admin123")
    a = ap.parse_args()

    token = call(f"{a.api_url}/auth/login", {"email": a.admin_email, "password": a.admin_password})["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    print(f"registering {a.gates * a.events} vehicles...")
    for g in range(a.gates):
        for i in range(a.events):
            try:
                call(f"{a.api_url}/sites/{SITE}/vehicles", {"plate": plate(g, i), "role": "resident"}, auth)
            except urllib.error.HTTPError as e:
                if e.code != 409:     # 409 = already registered from an earlier run
                    raise

    latencies, errors, lock = [], [], threading.Lock()
    base = datetime.now(timezone.utc) - timedelta(hours=1)

    def gate_worker(g):
        for i in range(a.events):
            for gate_id, offset in ((ENTRY, 0), (EXIT, 120)):
                body = {"site_id": SITE, "gate_id": gate_id, "plate": plate(g, i), "confidence": 0.9,
                        "captured_at": (base + timedelta(seconds=i * 300 + offset + g)).isoformat()}
                t0 = time.perf_counter()
                try:
                    call(f"{a.api_url}/detections", body, {"X-API-Key": a.api_key})
                    dt = time.perf_counter() - t0
                    with lock:
                        latencies.append(dt)
                except Exception as e:
                    with lock:
                        errors.append(repr(e))

    threads = [threading.Thread(target=gate_worker, args=(g,)) for g in range(a.gates)]
    t0 = time.perf_counter()
    [t.start() for t in threads]
    [t.join() for t in threads]
    wall = time.perf_counter() - t0

    if not latencies:
        raise SystemExit(f"all requests failed, e.g. {errors[:1]}")
    ms = sorted(x * 1000 for x in latencies)
    pct = lambda p: ms[min(len(ms) - 1, int(len(ms) * p))]
    print(f"\n{a.gates} gates x {a.events} cycles = {len(latencies) + len(errors)} detections in {wall:.1f}s")
    print(f"throughput: {len(latencies) / wall:.0f} detections/s | errors: {len(errors)}")
    print(f"latency ms: p50={statistics.median(ms):.0f}  p95={pct(0.95):.0f}  p99={pct(0.99):.0f}  max={ms[-1]:.0f}")
    if errors:
        print("first error:", errors[0])


if __name__ == "__main__":
    main()
