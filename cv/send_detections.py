
"""VistaLock CV integration preflight. This script never sends detections."""

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SITE_ID = "11111111-1111-1111-1111-111111111111"
GATES = {
    "entry": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "exit": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="output/reads.jsonl")
    parser.add_argument("--gate", choices=GATES, default="entry")
    parser.add_argument(
        "--video-start",
        required=True,
        help="Timezone-aware video start, e.g. 2026-10-24T21:28:36+05:30",
    )
    args = parser.parse_args()

    api_key = os.getenv("CV_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ERROR: CV_API_KEY is missing from the loaded environment.")

    try:
        site_id = str(UUID(SITE_ID))
        gate_id = str(UUID(GATES[args.gate]))
        video_start = datetime.fromisoformat(args.video_start)
    except ValueError as exc:
        raise SystemExit(f"ERROR: Invalid configuration: {exc}")

    if video_start.tzinfo is None or video_start.utcoffset() is None:
        raise SystemExit("ERROR: --video-start must include a timezone offset.")

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    if not input_path.is_file():
        raise SystemExit(f"ERROR: Results file not found: {input_path}")

    checked = 0
    errors = []
    print("VistaLock CV preflight — DRY RUN ONLY")
    print(f"Gate: Main {args.gate.title()}")
    print(f"Results file: {input_path}")
    print("API key: present (value hidden)")
    print("Network requests: DISABLED\n")

    with input_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                plate = str(record["plate"]).strip().upper()
                if not plate.isalnum() or not 4 <= len(plate) <= 12:
                    raise ValueError("plate must contain 4–12 letters/digits")

                offset = float(record["first_seen_s"])
                if offset < 0:
                    raise ValueError("first_seen_s cannot be negative")

                confidence = float(record["best_conf"])
                if not 0 <= confidence <= 1:
                    raise ValueError("best_conf must be between 0 and 1")

                captured_at = video_start + timedelta(seconds=offset)
                payload = {
                    "site_id": site_id,
                    "gate_id": gate_id,
                    "plate": plate,
                    "confidence": confidence,
                    "captured_at": captured_at.isoformat(),
                    "image": record.get("image"),
                }
                checked += 1
                print(f"Record {checked}: {json.dumps(payload)}")

            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"Line {line_number}: {exc}")

    print(f"\nValid records: {checked}")
    print(f"Invalid records: {len(errors)}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        raise SystemExit("Preflight FAILED. No requests were sent.")
    if checked == 0:
        raise SystemExit("No records to validate. No requests were sent.")

    print("\nPreflight PASSED. No detections were sent or written to the database.")


if __name__ == "__main__":
    main()
