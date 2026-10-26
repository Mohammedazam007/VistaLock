import os
import pathlib
import sys
import unicodedata
from urllib.parse import urlsplit

# The fixture drops/recreates public, so only a dedicated local test database is allowed.
# Policy: PostgreSQL URI, loopback host, explicit port 5432, and exact database gs_api_test.
# This deliberately rejects remote hosts and every other database name.
_TEST_HOSTS = {"localhost", "127.0.0.1", "::1"}
_TEST_PORT = 5432
_TEST_DATABASE = "gs_api_test"


def _validated_test_database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("TEST_DATABASE_URL must be explicitly set to the isolated gs_api_test database.")

    if url != url.strip() or any(c.isspace() or unicodedata.category(c) == "Cc" for c in url):
        raise RuntimeError("Unsafe TEST_DATABASE_URL; whitespace and control characters are not allowed.")
    if "?" in url or "#" in url:
        raise RuntimeError("Unsafe TEST_DATABASE_URL; query and fragment delimiters are not allowed.")

    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        database_path = parsed.path
    except ValueError:
        raise RuntimeError("Unsafe TEST_DATABASE_URL; expected a valid local test database URI.") from None

    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or host not in _TEST_HOSTS
        or port != _TEST_PORT
        or database_path != f"/{_TEST_DATABASE}"
        or "%" in database_path
        or not parsed.username
    ):
        raise RuntimeError(
            "Unsafe TEST_DATABASE_URL; expected a PostgreSQL URI for "
            "localhost:5432/gs_api_test with a username and no query or fragment."
        )
    return url


# Must be validated before importing the app or opening any DB connection.
TEST_DB = _validated_test_database_url()
os.environ["DATABASE_URL"] = TEST_DB
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.auth import create_token, hash_password
from app.main import app

DB_DIR = pathlib.Path(__file__).resolve().parents[2] / "db"
SCHEMA = DB_DIR / "schema.sql"
USERS_MIGRATION = DB_DIR / "migration_add_users.sql"

SITE = "11111111-1111-1111-1111-111111111111"
OTHER_SITE = "22222222-2222-2222-2222-222222222222"
ENTRY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ENTRY2 = "cccccccc-cccc-cccc-cccc-cccccccccccc"
EXIT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OTHER_GATE = "dddddddd-dddd-dddd-dddd-dddddddddddd"

ADMIN_ID = "a0000000-0000-0000-0000-000000000001"
GUARD_ID = "a0000000-0000-0000-0000-000000000002"
RESIDENT_ID = "a0000000-0000-0000-0000-000000000003"
OTHER_ADMIN_ID = "a0000000-0000-0000-0000-000000000004"
PASSWORD = "test-password"
PASSWORD_HASH = hash_password(PASSWORD)   # hashed once: scrypt is deliberately slow
CV_KEY = "dev-cv-key"


@pytest.fixture(scope="session", autouse=True)
def schema():
    try:
        connection = psycopg.connect(TEST_DB, autocommit=True)
    except psycopg.Error:
        raise RuntimeError("Unable to connect to the isolated test database.") from None
    with connection as c:
        actual_database = c.execute("SELECT current_database()").fetchone()[0]
        if actual_database != _TEST_DATABASE:
            raise RuntimeError("Connected database is not the approved isolated test database.")
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.execute(SCHEMA.read_text())
        c.execute(USERS_MIGRATION.read_text())


@pytest.fixture(autouse=True)
def fresh_data(schema):
    try:
        connection = psycopg.connect(TEST_DB, autocommit=True)
    except psycopg.Error:
        raise RuntimeError("Unable to connect to the isolated test database.") from None
    with connection as c:
        c.execute("TRUNCATE sites CASCADE")
        c.execute(f"""
          INSERT INTO sites (id, name, type) VALUES ('{SITE}', 'Test Apartments', 'apartment'),
                                                    ('{OTHER_SITE}', 'Other Office', 'office');
          INSERT INTO gates (id, site_id, name, direction) VALUES
            ('{ENTRY}', '{SITE}', 'Entry 1', 'entry'),
            ('{ENTRY2}', '{SITE}', 'Entry 2', 'entry'),
            ('{EXIT}', '{SITE}', 'Exit', 'exit'),
            ('{OTHER_GATE}', '{OTHER_SITE}', 'Other gate', 'entry');
          INSERT INTO vehicles (site_id, plate, owner_name, role) VALUES
            ('{SITE}', 'TS09AB1234', 'Ravi', 'resident'),
            ('{SITE}', 'TS08CD5678', 'Anita', 'staff'),
            ('{SITE}', 'TS10EF9999', 'Bad', 'blacklisted');
          INSERT INTO users (id, site_id, email, password_hash, role, unit, full_name) VALUES
            ('{ADMIN_ID}', '{SITE}', 'admin@test.io', '{PASSWORD_HASH}', 'admin', NULL, 'Admin'),
            ('{GUARD_ID}', '{SITE}', 'guard@test.io', '{PASSWORD_HASH}', 'security', NULL, 'Guard'),
            ('{RESIDENT_ID}', '{SITE}', 'ravi@test.io', '{PASSWORD_HASH}', 'resident', 'A-101', 'Ravi Kumar'),
            ('{OTHER_ADMIN_ID}', '{OTHER_SITE}', 'boss@other.io', '{PASSWORD_HASH}', 'admin', NULL, 'Other Admin');
        """)


@pytest.fixture(scope="session")
def client():  # one app lifespan for the whole run: the pool cannot be reopened
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with psycopg.connect(TEST_DB, row_factory=dict_row, autocommit=True) as c:
        yield c


class Authed:
    """TestClient wrapper that adds fixed headers to every request."""
    def __init__(self, client, headers):
        self.c, self.h = client, headers

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self.h, **kw)


def _bearer(user_id):
    return {"Authorization": f"Bearer {create_token(user_id)}"}


@pytest.fixture
def admin(client):
    return Authed(client, _bearer(ADMIN_ID))


@pytest.fixture
def guard(client):
    return Authed(client, _bearer(GUARD_ID))


@pytest.fixture
def resident(client):
    return Authed(client, _bearer(RESIDENT_ID))


@pytest.fixture
def other_admin(client):
    return Authed(client, _bearer(OTHER_ADMIN_ID))


@pytest.fixture
def cv(client):
    return Authed(client, {"X-API-Key": CV_KEY})


@pytest.fixture
def anon(client):
    return Authed(client, {})
