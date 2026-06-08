import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

_connection = None

def get_connection():
    global _connection
    try:
        if _connection is None or _connection.closed != 0:
            _connection = psycopg2.connect(DATABASE_URL)
            _connection.autocommit = True
        # Simple test
        with _connection.cursor() as cur:
            cur.execute("SELECT 1")
    except psycopg2.Error:
        _connection = psycopg2.connect(DATABASE_URL)
        _connection.autocommit = True
    return _connection

def query(sql: str, params: tuple = None) -> list:
    """Executes a read-only query and returns a list of dicts."""
    sql_upper = sql.upper()
    forbidden_keywords = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "TRUNCATE ", "GRANT ", "REVOKE "]
    for keyword in forbidden_keywords:
        if keyword in sql_upper:
            raise ValueError(f"Read-only enforcement: SQL contains forbidden keyword '{keyword.strip()}'")
    
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            conn.rollback()
            raise e
