import os
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", "water_tracker.db")


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Initialize database tables."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                daily_goal_ml INTEGER DEFAULT 2000,
                reminder_interval_hours INTEGER DEFAULT 2,
                active_hours_start INTEGER DEFAULT 8,
                active_hours_end INTEGER DEFAULT 22,
                reminders_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS water_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_ml INTEGER NOT NULL,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_water_logs_user_date
            ON water_logs (user_id, logged_at)
        """)


def get_or_create_user(user_id: int) -> dict:
    """Get user settings or create with defaults."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row:
            return dict(row)

        cursor.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (user_id,)
        )

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(cursor.fetchone())


def update_user_setting(user_id: int, setting: str, value) -> None:
    """Update a user setting."""
    allowed_settings = {
        "daily_goal_ml",
        "reminder_interval_hours",
        "active_hours_start",
        "active_hours_end",
        "reminders_enabled"
    }

    if setting not in allowed_settings:
        raise ValueError(f"Invalid setting: {setting}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {setting} = ? WHERE user_id = ?",
            (value, user_id)
        )


def log_water(user_id: int, amount_ml: int) -> None:
    """Log water intake."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO water_logs (user_id, amount_ml) VALUES (?, ?)",
            (user_id, amount_ml)
        )


def get_today_total(user_id: int) -> int:
    """Get total water intake for today."""
    today = date.today().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount_ml), 0) as total
            FROM water_logs
            WHERE user_id = ? AND DATE(logged_at) = ?
            """,
            (user_id, today)
        )
        return cursor.fetchone()["total"]


def get_history(user_id: int, days: int = 7) -> list[dict]:
    """Get daily totals for past N days."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get totals grouped by date
        cursor.execute(
            """
            SELECT DATE(logged_at) as log_date, SUM(amount_ml) as total
            FROM water_logs
            WHERE user_id = ? AND logged_at >= DATE('now', ?)
            GROUP BY DATE(logged_at)
            ORDER BY log_date DESC
            """,
            (user_id, f"-{days} days")
        )

        # Convert to dict for easy lookup
        totals = {row["log_date"]: row["total"] for row in cursor.fetchall()}

        # Build complete list with all days (including zero days)
        result = []
        for i in range(days):
            d = date.today() - timedelta(days=i)
            date_str = d.isoformat()
            result.append({
                "date": d,
                "total": totals.get(date_str, 0)
            })

        return result


def get_all_users_with_reminders() -> list[dict]:
    """Get all users with reminders enabled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE reminders_enabled = 1"
        )
        return [dict(row) for row in cursor.fetchall()]


def clear_today(user_id: int) -> int:
    """Clear all water logs for today. Returns number of deleted entries."""
    today = date.today().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM water_logs WHERE user_id = ? AND DATE(logged_at) = ?",
            (user_id, today)
        )
        return cursor.rowcount


def undo_last_drink(user_id: int) -> int:
    """Remove the last drink entry for today. Returns the amount removed, or 0 if none."""
    today = date.today().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        # Get the last entry
        cursor.execute(
            """
            SELECT id, amount_ml FROM water_logs
            WHERE user_id = ? AND DATE(logged_at) = ?
            ORDER BY logged_at DESC LIMIT 1
            """,
            (user_id, today)
        )
        row = cursor.fetchone()

        if not row:
            return 0

        # Delete it
        cursor.execute("DELETE FROM water_logs WHERE id = ?", (row["id"],))
        return row["amount_ml"]
