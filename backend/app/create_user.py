"""Create a dashboard user from the command line.

    python -m app.create_user --email admin@example.com --password 's3cret!' --role admin \
        --site-id 11111111-1111-1111-1111-111111111111 --name "Site Admin"
"""
import argparse

import psycopg

from .auth import hash_password
from .db import DATABASE_URL


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--role", required=True, choices=["admin", "security", "resident"])
    p.add_argument("--site-id", required=True)
    p.add_argument("--unit", help="required for residents, e.g. A-101")
    p.add_argument("--name")
    a = p.parse_args()
    if a.role == "resident" and not a.unit:
        p.error("residents need --unit")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO users (site_id, email, password_hash, role, unit, full_name) VALUES (%s,%s,%s,%s,%s,%s)",
            (a.site_id, a.email.lower().strip(), hash_password(a.password), a.role, a.unit, a.name))
    print(f"created {a.role} {a.email}")


if __name__ == "__main__":
    main()
