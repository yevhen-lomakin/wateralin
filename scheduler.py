import logging
from datetime import datetime, timedelta
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

    # Check if within active hours
    current_hour = datetime.now().hour
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
