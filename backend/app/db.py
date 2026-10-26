import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://gatesense:gatesense_dev@localhost:5432/gatesense"
)

# Opened/closed by the FastAPI lifespan in main.py
pool = ConnectionPool(
    DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False
)


def get_conn():
    """FastAPI dependency: one pooled connection per request, committed on success."""
    with pool.connection() as conn:
        yield conn
