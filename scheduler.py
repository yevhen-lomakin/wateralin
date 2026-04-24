import logging
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from handlers import get_quick_drink_keyboard, progress_bar

logger = logging.getLogger(__name__)


def get_job_name(user_id: int) -> str:
    """Get unique job name for user."""
    return f"reminder_{user_id}"


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send water reminder to user."""
    user_id = context.job.data["user_id"]
    user = db.get_or_create_user(user_id)

    # Check if within active hours (in user's timezone)
    try:
        user_tz = ZoneInfo(user.get("timezone", "UTC"))
    except Exception:
        user_tz = ZoneInfo("UTC")
    current_hour = datetime.now(user_tz).hour
    if not (user["active_hours_start"] <= current_hour < user["active_hours_end"]):
        logger.info(f"Skipping reminder for {user_id}: outside active hours ({current_hour})")
        return

    # Check if reminders still enabled
    if not user["reminders_enabled"]:
        logger.info(f"Skipping reminder for {user_id}: reminders disabled")
        return

    total = db.get_today_total(user_id)
    goal = user["daily_goal_ml"]

    # Don't remind if goal already reached
    if total >= goal:
        logger.info(f"Skipping reminder for {user_id}: goal reached")
        return

    percentage = min(int(total / goal * 100), 100) if goal > 0 else 0
    bar = progress_bar(total, goal)

    message = "💧 Time to drink water!\n\n"
    message += f"Today: {total}/{goal}ml {bar} {percentage}%"

    try:
        result = await context.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=get_quick_drink_keyboard()
        )
        logger.info(f"Sent reminder to {user_id}, message_id={result.message_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder to {user_id}: {e}")


def remove_user_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Remove existing reminder job for user."""
    job_name = get_job_name(user_id)
    current_jobs = context.job_queue.get_jobs_by_name(job_name)

    for job in current_jobs:
        job.schedule_removal()


async def setup_user_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Setup or update reminder job for user."""
    user = db.get_or_create_user(user_id)

    # Remove existing job
    remove_user_reminder(context, user_id)

    # Don't schedule if reminders disabled
    if not user["reminders_enabled"]:
        logger.info(f"Reminders disabled for {user_id}, not scheduling")
        return

    job_name = get_job_name(user_id)
    interval_hours = user["reminder_interval_hours"]

    # Schedule repeating job - first reminder after 10 seconds, then at interval
    context.job_queue.run_repeating(
        callback=send_reminder,
        interval=timedelta(hours=interval_hours),
        first=timedelta(seconds=10),
        name=job_name,
        data={"user_id": user_id}
    )
    logger.info(f"Scheduled reminders for {user_id} every {interval_hours}h")


async def restore_all_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restore reminders for all users on bot startup."""
    users = db.get_all_users_with_reminders()
    logger.info(f"Restoring reminders for {len(users)} users")

    for user in users:
        await setup_user_reminder(context, user["user_id"])


# --- Pill reminder functions ---


def get_pill_job_name(pill_id: int, hour: int, minute: int) -> str:
    """Get unique job name for pill reminder."""
    return f"pill_{pill_id}_{hour}_{minute}"


def get_pill_followup_job_name(pill_id: int) -> str:
    """Get unique job name for pill follow-up reminders."""
    return f"pill_followup_{pill_id}"


async def send_pill_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send pill reminder to user."""
    data = context.job.data
    user_id = data["user_id"]
    pill_id = data["pill_id"]
    pill_name = data["pill_name"]

    # Check if already taken today
    today_logs = db.get_today_pill_logs(user_id)
    already_taken = any(log["pill_id"] == pill_id for log in today_logs)
    if already_taken:
        logger.info(f"Skipping pill reminder for {user_id}: {pill_name} already taken")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Taken {pill_name}", callback_data=f"pill_taken:{pill_id}")],
    ])

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💊 Time to take {pill_name}!",
            reply_markup=keyboard
        )
        logger.info(f"Sent pill reminder to {user_id}: {pill_name}")
    except Exception as e:
        logger.error(f"Failed to send pill reminder to {user_id}: {e}")

    # Schedule follow-up reminders every 30 min until taken
    schedule_pill_followup(context, pill_id, pill_name, user_id)


async def send_pill_followup_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send follow-up pill reminder every 30 min until marked as taken."""
    data = context.job.data
    user_id = data["user_id"]
    pill_id = data["pill_id"]
    pill_name = data["pill_name"]

    # Check if taken — cancel follow-ups if so
    today_logs = db.get_today_pill_logs(user_id)
    already_taken = any(log["pill_id"] == pill_id for log in today_logs)
    if already_taken:
        logger.info(f"Pill {pill_name} taken, cancelling follow-up for {user_id}")
        cancel_pill_followup(context, pill_id)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Taken {pill_name}", callback_data=f"pill_taken:{pill_id}")],
    ])

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⏰ Reminder: take {pill_name}!",
            reply_markup=keyboard
        )
        logger.info(f"Sent pill follow-up to {user_id}: {pill_name}")
    except Exception as e:
        logger.error(f"Failed to send pill follow-up to {user_id}: {e}")


def schedule_pill_followup(context: ContextTypes.DEFAULT_TYPE, pill_id: int,
                           pill_name: str, user_id: int) -> None:
    """Schedule repeating follow-up reminders every 30 min for an untaken pill."""
    job_name = get_pill_followup_job_name(pill_id)

    # Remove any existing follow-up for this pill
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    context.job_queue.run_repeating(
        callback=send_pill_followup_reminder,
        interval=timedelta(minutes=30),
        first=timedelta(minutes=30),
        name=job_name,
        data={"user_id": user_id, "pill_id": pill_id, "pill_name": pill_name}
    )
    logger.info(f"Scheduled pill follow-up every 30 min: {pill_name} for user {user_id}")


def cancel_pill_followup(context: ContextTypes.DEFAULT_TYPE, pill_id: int) -> None:
    """Cancel follow-up reminders for a pill."""
    job_name = get_pill_followup_job_name(pill_id)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    logger.info(f"Cancelled pill follow-up for pill {pill_id}")


def setup_pill_reminder(context: ContextTypes.DEFAULT_TYPE, pill_id: int, pill_name: str,
                        user_id: int, hour: int, minute: int, user_timezone: str = "UTC") -> None:
    """Schedule a daily pill reminder at a specific time."""
    job_name = get_pill_job_name(pill_id, hour, minute)

    # Remove existing job if any
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    target_time = dt_time(hour=hour, minute=minute, tzinfo=tz)

    context.job_queue.run_daily(
        callback=send_pill_reminder,
        time=target_time,
        name=job_name,
        data={"user_id": user_id, "pill_id": pill_id, "pill_name": pill_name}
    )
    logger.info(f"Scheduled pill reminder: {pill_name} at {hour:02d}:{minute:02d} for user {user_id}")


def remove_pill_reminders(context: ContextTypes.DEFAULT_TYPE, pill_id: int) -> None:
    """Remove all scheduled reminder jobs for a pill (including follow-ups)."""
    pill = db.get_pill(pill_id)
    if not pill:
        return
    for reminder in pill["reminders"]:
        job_name = get_pill_job_name(pill_id, reminder["remind_at_hour"], reminder["remind_at_minute"])
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
    cancel_pill_followup(context, pill_id)


async def restore_all_pill_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restore all pill reminders on bot startup."""
    reminders = db.get_all_pill_reminders()
    logger.info(f"Restoring {len(reminders)} pill reminders")

    for r in reminders:
        user = db.get_or_create_user(r["user_id"])
        setup_pill_reminder(
            context, r["pill_id"], r["pill_name"],
            r["user_id"], r["remind_at_hour"], r["remind_at_minute"],
            user.get("timezone", "UTC")
        )


# --- Routine reminder functions ---


def get_routine_job_name(routine_id: int) -> str:
    """Get unique job name for a routine's daily reminder."""
    return f"routine_{routine_id}"


def get_routine_followup_job_name(routine_id: int) -> str:
    """Get unique job name for a routine's follow-up reminder."""
    return f"routine_followup_{routine_id}"


def _user_tz(user: dict) -> ZoneInfo:
    try:
        return ZoneInfo(user.get("timezone", "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _due_not_taken_items(routine_id: int, user_id: int, user_tz: ZoneInfo) -> list[dict]:
    """Return routine items that are due today in user's tz AND not yet logged."""
    today = datetime.now(user_tz).date()
    routine = db.get_routine(routine_id, today=today)
    if not routine:
        return []
    today_logs = db.get_today_routine_item_logs(user_id, today=today)
    taken_ids = {log["routine_item_id"] for log in today_logs}
    return [
        item for item in routine["items"]
        if item["due_today"] and item["id"] not in taken_ids
    ]


def _build_routine_reminder(routine_name: str, items: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    """Build the reminder message text and button markup for a routine."""
    has_cream = any(i["type"] == "cream" for i in items)
    has_pill = any(i["type"] == "pill" for i in items)
    emoji = ""
    if has_cream:
        emoji += "🧴"
    if has_pill:
        emoji += "💊"
    if has_cream and not has_pill:
        verb = "apply"
    elif has_pill and not has_cream:
        verb = "take"
    else:
        verb = "apply/take"
    text = f"{emoji} {routine_name} — time to {verb}!"
    buttons = [
        [InlineKeyboardButton(
            f"Taken: {item['name']}",
            callback_data=f"routine_item_taken:{item['id']}"
        )]
        for item in items
    ]
    return text, InlineKeyboardMarkup(buttons)


async def send_routine_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the daily routine reminder; schedule follow-up if items are due."""
    data = context.job.data
    routine_id = data["routine_id"]
    user_id = data["user_id"]
    user = db.get_or_create_user(user_id)
    user_tz = _user_tz(user)

    due = _due_not_taken_items(routine_id, user_id, user_tz)
    if not due:
        logger.info(f"Routine {routine_id}: nothing due/untaken, skipping")
        return

    routine = db.get_routine(routine_id)
    if not routine:
        return
    text, markup = _build_routine_reminder(routine["name"], due)
    try:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
        logger.info(f"Sent routine reminder {routine_id} to {user_id}")
    except Exception as e:
        logger.error(f"Failed to send routine reminder {routine_id}: {e}")

    schedule_routine_followup(context, routine_id, user_id)


async def send_routine_followup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Follow-up reminder every 30 min until all due items are marked taken."""
    data = context.job.data
    routine_id = data["routine_id"]
    user_id = data["user_id"]
    user = db.get_or_create_user(user_id)
    user_tz = _user_tz(user)

    due = _due_not_taken_items(routine_id, user_id, user_tz)
    if not due:
        logger.info(f"Routine {routine_id}: all taken, cancelling follow-up")
        cancel_routine_followup(context, routine_id)
        return

    routine = db.get_routine(routine_id)
    if not routine:
        cancel_routine_followup(context, routine_id)
        return
    text, markup = _build_routine_reminder(routine["name"], due)
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⏰ {text}",
            reply_markup=markup,
        )
        logger.info(f"Sent routine follow-up {routine_id} to {user_id}")
    except Exception as e:
        logger.error(f"Failed to send routine follow-up {routine_id}: {e}")


def schedule_routine_followup(context: ContextTypes.DEFAULT_TYPE,
                              routine_id: int, user_id: int) -> None:
    """Start repeating 30-min follow-up for a routine."""
    job_name = get_routine_followup_job_name(routine_id)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    context.job_queue.run_repeating(
        callback=send_routine_followup,
        interval=timedelta(minutes=30),
        first=timedelta(minutes=30),
        name=job_name,
        data={"routine_id": routine_id, "user_id": user_id},
    )
    logger.info(f"Scheduled routine follow-up every 30 min for routine {routine_id}")


def cancel_routine_followup(context: ContextTypes.DEFAULT_TYPE, routine_id: int) -> None:
    """Cancel any running follow-up for a routine."""
    job_name = get_routine_followup_job_name(routine_id)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()


def setup_routine_reminder(context: ContextTypes.DEFAULT_TYPE, routine_id: int,
                           user_id: int, hour: int, minute: int,
                           user_timezone: str = "UTC") -> None:
    """Create/replace the daily run_daily job for a routine."""
    job_name = get_routine_job_name(routine_id)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    target_time = dt_time(hour=hour, minute=minute, tzinfo=tz)
    context.job_queue.run_daily(
        callback=send_routine_reminder,
        time=target_time,
        name=job_name,
        data={"routine_id": routine_id, "user_id": user_id},
    )
    logger.info(
        f"Scheduled routine reminder {routine_id} at {hour:02d}:{minute:02d}"
    )


def remove_routine_reminder(context: ContextTypes.DEFAULT_TYPE, routine_id: int) -> None:
    """Remove both daily and follow-up jobs for a routine."""
    job_name = get_routine_job_name(routine_id)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    cancel_routine_followup(context, routine_id)


async def restore_all_routine_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restore all routine reminders on bot startup."""
    routines = db.get_all_routines_for_scheduler()
    logger.info(f"Restoring {len(routines)} routine reminders")
    for r in routines:
        user = db.get_or_create_user(r["user_id"])
        setup_routine_reminder(
            context, r["id"], r["user_id"],
            r["remind_at_hour"], r["remind_at_minute"],
            user.get("timezone", "UTC"),
        )
