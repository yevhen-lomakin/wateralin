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
                timezone TEXT DEFAULT 'UTC',
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                remind_at_hour INTEGER NOT NULL,
                remind_at_minute INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routine_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routine_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('cream', 'pill')),
                name TEXT NOT NULL,
                period_days INTEGER NOT NULL DEFAULT 1,
                start_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (routine_id) REFERENCES routines (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routine_item_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routine_item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (routine_item_id) REFERENCES routine_items (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_routine_item_logs_user_date
            ON routine_item_logs (user_id, applied_at)
        """)

        # Migration: add timezone column if missing
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if "timezone" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'UTC'")


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
        "reminders_enabled",
        "timezone"
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


# --- Routine functions ---


def _is_item_due_on(start_date: date, period_days: int, on_date: date) -> bool:
    """Check if an item is due on a given date based on its period."""
    if on_date < start_date:
        return False
    return (on_date - start_date).days % period_days == 0


def _hydrate_routine_items(items: list[dict], today: date) -> list[dict]:
    """Convert start_date strings to dates and add due_today flag."""
    for item in items:
        sd = date.fromisoformat(item["start_date"])
        item["start_date"] = sd
        item["due_today"] = _is_item_due_on(sd, item["period_days"], today)
    return items


def add_routine(user_id: int, name: str, hour: int, minute: int = 0) -> int:
    """Add a new routine. Returns routine id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO routines (user_id, name, remind_at_hour, remind_at_minute) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, hour, minute)
        )
        return cursor.lastrowid


def get_user_routines(user_id: int, today: Optional[date] = None) -> list[dict]:
    """Get all routines for a user, each with its items list."""
    if today is None:
        today = date.today()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM routines WHERE user_id = ? "
            "ORDER BY remind_at_hour, remind_at_minute",
            (user_id,)
        )
        routines = [dict(row) for row in cursor.fetchall()]
        for r in routines:
            cursor.execute(
                "SELECT * FROM routine_items WHERE routine_id = ? ORDER BY id",
                (r["id"],)
            )
            items = [dict(row) for row in cursor.fetchall()]
            r["items"] = _hydrate_routine_items(items, today)
        return routines


def get_routine(routine_id: int, today: Optional[date] = None) -> Optional[dict]:
    """Get a single routine with its items."""
    if today is None:
        today = date.today()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routines WHERE id = ?", (routine_id,))
        row = cursor.fetchone()
        if not row:
            return None
        routine = dict(row)
        cursor.execute(
            "SELECT * FROM routine_items WHERE routine_id = ? ORDER BY id",
            (routine_id,)
        )
        items = [dict(r) for r in cursor.fetchall()]
        routine["items"] = _hydrate_routine_items(items, today)
        return routine


def delete_routine(routine_id: int) -> None:
    """Delete a routine and all its items and logs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM routine_item_logs
            WHERE routine_item_id IN (
                SELECT id FROM routine_items WHERE routine_id = ?
            )
            """,
            (routine_id,)
        )
        cursor.execute("DELETE FROM routine_items WHERE routine_id = ?", (routine_id,))
        cursor.execute("DELETE FROM routines WHERE id = ?", (routine_id,))


def update_routine_time(routine_id: int, hour: int, minute: int = 0) -> None:
    """Update a routine's reminder time."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE routines SET remind_at_hour = ?, remind_at_minute = ? WHERE id = ?",
            (hour, minute, routine_id)
        )


def add_routine_item(routine_id: int, item_type: str, name: str,
                     period_days: int, start_date: date) -> int:
    """Add a cream or pill item to a routine. Returns item id."""
    if item_type not in ("cream", "pill"):
        raise ValueError(f"Invalid item type: {item_type}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO routine_items (routine_id, type, name, period_days, start_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (routine_id, item_type, name, period_days, start_date.isoformat())
        )
        return cursor.lastrowid


def get_routine_item(item_id: int) -> Optional[dict]:
    """Get a single routine item."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routine_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            return None
        item = dict(row)
        item["start_date"] = date.fromisoformat(item["start_date"])
        return item


def delete_routine_item(item_id: int) -> None:
    """Delete a routine item and its logs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM routine_item_logs WHERE routine_item_id = ?", (item_id,))
        cursor.execute("DELETE FROM routine_items WHERE id = ?", (item_id,))


def log_routine_item_taken(item_id: int, user_id: int) -> None:
    """Log that a routine item was applied/taken."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO routine_item_logs (routine_item_id, user_id) VALUES (?, ?)",
            (item_id, user_id)
        )


def get_today_routine_item_logs(user_id: int, today: Optional[date] = None) -> list[dict]:
    """Get routine item logs for today."""
    if today is None:
        today = date.today()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rl.routine_item_id, rl.applied_at, ri.name, ri.routine_id, ri.type
            FROM routine_item_logs rl
            JOIN routine_items ri ON ri.id = rl.routine_item_id
            WHERE rl.user_id = ? AND DATE(rl.applied_at) = ?
            ORDER BY rl.applied_at
            """,
            (user_id, today.isoformat())
        )
        return [dict(row) for row in cursor.fetchall()]


def get_routine_history(user_id: int, days: int = 7) -> list[dict]:
    """Return per-day history for last N days.
    Each entry: {date, routines: [{name, items: [{name, type, taken}]}]}.
    Only items that were due on the given day are included.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM routines WHERE user_id = ? "
            "ORDER BY remind_at_hour, remind_at_minute",
            (user_id,)
        )
        routines = [dict(r) for r in cursor.fetchall()]
        for r in routines:
            cursor.execute(
                "SELECT * FROM routine_items WHERE routine_id = ? ORDER BY id",
                (r["id"],)
            )
            items = []
            for row in cursor.fetchall():
                item = dict(row)
                item["start_date"] = date.fromisoformat(item["start_date"])
                items.append(item)
            r["items"] = items

        result = []
        for i in range(days):
            d = date.today() - timedelta(days=i)
            cursor.execute(
                """
                SELECT routine_item_id FROM routine_item_logs
                WHERE user_id = ? AND DATE(applied_at) = ?
                """,
                (user_id, d.isoformat())
            )
            taken_ids = {row["routine_item_id"] for row in cursor.fetchall()}

            day_routines = []
            for r in routines:
                due_items = []
                for item in r["items"]:
                    if item["start_date"] > d:
                        continue
                    if _is_item_due_on(item["start_date"], item["period_days"], d):
                        due_items.append({
                            "name": item["name"],
                            "type": item["type"],
                            "taken": item["id"] in taken_ids,
                        })
                if due_items:
                    day_routines.append({"name": r["name"], "items": due_items})

            result.append({"date": d, "routines": day_routines})
        return result


def get_all_routines_for_scheduler() -> list[dict]:
    """Get all routines for startup scheduler restoration."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routines")
        return [dict(row) for row in cursor.fetchall()]


def delete_today_routine_item_log(item_id: int, user_id: int,
                                  today: Optional[date] = None) -> int:
    """Delete any routine_item_logs rows for this item+user dated today.

    Returns the number of rows deleted. Idempotent: returns 0 if none exist.
    """
    if today is None:
        today = date.today()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM routine_item_logs
            WHERE routine_item_id = ? AND user_id = ? AND DATE(applied_at) = ?
            """,
            (item_id, user_id, today.isoformat())
        )
        return cursor.rowcount
