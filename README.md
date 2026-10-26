# GateSense

Multi-site vehicle access management: plate recognition + registry, visitor passes,
entry/exit logs, alerts. Runs fully on a laptop (recorded videos / webcam, simulated gate).

## Layout
- `db/`        Postgres schema + dev seed data
- `cv/`        Plate detection + OCR pipeline (separate service)
- `backend/`   FastAPI: entry/exit logic, rules engine, visitor passes
- `dashboard/` React dashboard: logs, "currently inside", alerts
- `data/`      Test videos and plate crops (git-ignored)

## Run the database
    cp .env.example .env
    docker compose up -d
    docker compose exec db psql -U gatesense -d gatesense -c "\dt"

The schema, users table, and seed run only on the first start of an empty volume. Existing database volumes are left unchanged; apply `db/migration_add_users.sql` separately to an existing database that does not yet have the users table.
To reset everything: `docker compose down -v && docker compose up -d`

## Plate pipeline (cv/)
    cd cv
    python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python -m pytest -q                                    # plate logic + voting tests
    python read_video.py ../data/videos/entry.mp4 --verbose

First run downloads the EasyOCR models (~100 MB). Put test videos in `data/videos/`.
Use `--roi x,y,w,h` to read only the gate lane, and `--every N` to trade speed for accuracy.
