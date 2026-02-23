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
    """Remove all scheduled reminder jobs for a pill."""
    pill = db.get_pill(pill_id)
    if not pill:
        return
    for reminder in pill["reminders"]:
        job_name = get_pill_job_name(pill_id, reminder["remind_at_hour"], reminder["remind_at_minute"])
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()


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
