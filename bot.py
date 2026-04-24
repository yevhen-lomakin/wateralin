import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

import database as db
from handlers import (
    start_command,
    drink_command,
    today_command,
    history_command,
    settings_command,
    button_callback,
    text_message_handler
)
from scheduler import (
    restore_all_reminders,
    restore_all_pill_reminders,
    restore_all_routine_reminders,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Initialize database and restore reminders after bot starts."""
    db.init_db()
    await restore_all_reminders(application)
    await restore_all_pill_reminders(application)
    await restore_all_routine_reminders(application)
    logger.info("Bot initialized, reminders restored")


def main() -> None:
    """Start the bot."""
    token = os.getenv("BOT_TOKEN")

    if not token:
        logger.error("BOT_TOKEN not found in environment variables")
        return

    # Create application
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("drink", drink_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("settings", settings_command))

    # Register callback handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Register text message handler (for pill name input)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Run the bot
    logger.info("Starting bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
