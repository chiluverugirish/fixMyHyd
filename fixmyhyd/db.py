import os
import sqlite3


def get_db():
    database_url = os.getenv("DATABASE_URL")
    if database_url and ("postgresql" in database_url or "postgres" in database_url):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            return conn, True
        except Exception as e:
            print(f"PostgreSQL failed, falling back to SQLite: {e}")

    db_path = "/tmp/fixmyhyd.db" if "/opt/render" in os.getcwd() else os.getenv("DATABASE_PATH", "fixmyhyd.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn, False


class DBConnection:
    """Wrapper for both SQLite and PostgreSQL connections."""

    def __init__(self, conn, is_postgres):
        self._conn = conn
        self._is_postgres = is_postgres

    def execute(self, query, params=()):
        if self._is_postgres:
            query = query.replace("?", "%s")
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            return cursor
        return self._conn.execute(query, params)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def rollback(self):
        self._conn.rollback()

    def fetchscalar(self, query, params=()):
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return list(row.values())[0]
        return row[0]


def get_db_connection():
    conn, pg = get_db()
    return DBConnection(conn, pg)


def init_database(hash_password):
    conn, pg = get_db()
    cursor = conn.cursor()
    ph = "%s" if pg else "?"

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT NOT NULL,
            phone TEXT,
            telegram_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS admins (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS complaints (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            ghmc_id TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT,
            zone TEXT,
            gps_lat REAL,
            gps_lng REAL,
            status TEXT DEFAULT 'Submitted',
            submitted_by TEXT DEFAULT 'Citizen',
            source TEXT DEFAULT 'portal',
            user_id INTEGER,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    if pg:
        try:
            cursor.execute("SAVEPOINT migration_image_path")
            cursor.execute("ALTER TABLE complaints ADD COLUMN image_path TEXT")
            cursor.execute("RELEASE SAVEPOINT migration_image_path")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT migration_image_path")
    else:
        try:
            cursor.execute("ALTER TABLE complaints ADD COLUMN image_path TEXT")
            conn.commit()
        except Exception:
            pass

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS status_history (
            id {"SERIAL" if pg else "INTEGER"} PRIMARY KEY {"" if pg else "AUTOINCREMENT"},
            complaint_id INTEGER,
            old_status TEXT,
            new_status TEXT,
            changed_by TEXT,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute("SELECT COUNT(*) FROM admins")
    result = cursor.fetchone()
    admin_count = result["count"] if isinstance(result, dict) else result[0]
    if admin_count == 0:
        pw = hash_password("admin123")
        cursor.execute(
            f"INSERT INTO admins (username, password_hash, name) VALUES ({ph}, {ph}, {ph})",
            ("admin", pw, "System Administrator"),
        )

    conn.commit()
    cursor.close()
    conn.close()
