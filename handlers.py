from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db


def progress_bar(current: int, goal: int, length: int = 10) -> str:
    """Generate a text progress bar."""
    if goal <= 0:
        return "🙁" * length

    ratio = min(current / goal, 1.0)
    filled = int(ratio * length)
    empty = length - filled

    return "💧" * filled + "🙁" * empty


def get_quick_drink_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with quick drink buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+100ml", callback_data="drink:100"),
            InlineKeyboardButton("+250ml", callback_data="drink:250"),
            InlineKeyboardButton("+500ml", callback_data="drink:500"),
        ],
        [
            InlineKeyboardButton("Undo", callback_data="adjust:undo"),
            InlineKeyboardButton("Reset", callback_data="adjust:reset_confirm"),
        ],
        [
            InlineKeyboardButton("Today", callback_data="menu:today"),
            InlineKeyboardButton("History", callback_data="menu:history"),
            InlineKeyboardButton("Settings", callback_data="settings:menu"),
        ]
    ])


def get_settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    """Get settings menu keyboard."""
    reminders_status = "ON" if user["reminders_enabled"] else "OFF"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"Daily Goal: {user['daily_goal_ml']}ml",
            callback_data="settings:goal"
        )],
        [InlineKeyboardButton(
            f"Reminder Interval: {user['reminder_interval_hours']}h",
            callback_data="settings:interval"
        )],
        [InlineKeyboardButton(
            f"Active Hours: {user['active_hours_start']}:00-{user['active_hours_end']}:00",
            callback_data="settings:hours"
        )],
        [InlineKeyboardButton(
            f"Reminders: {reminders_status}",
            callback_data="settings:toggle_reminders"
        )],
        [InlineKeyboardButton("Back", callback_data="menu:main")],
    ])


def get_goal_keyboard() -> InlineKeyboardMarkup:
    """Get goal selection keyboard."""
    goals = [1500, 2000, 2500, 3000, 3500, 4000]
    buttons = []

    for i in range(0, len(goals), 3):
        row = [
            InlineKeyboardButton(f"{g}ml", callback_data=f"goal:{g}")
            for g in goals[i:i+3]
        ]
        buttons.append(row)

    buttons.append([InlineKeyboardButton("Back", callback_data="settings:back")])
    return InlineKeyboardMarkup(buttons)


def get_interval_keyboard() -> InlineKeyboardMarkup:
    """Get reminder interval selection keyboard."""
    intervals = [1, 2, 3, 4]
    buttons = [[
        InlineKeyboardButton(f"{h}h", callback_data=f"interval:{h}")
        for h in intervals
    ]]
    buttons.append([InlineKeyboardButton("Back", callback_data="settings:back")])
    return InlineKeyboardMarkup(buttons)


def get_hours_keyboard(setting_type: str) -> InlineKeyboardMarkup:
    """Get active hours selection keyboard."""
    hours = list(range(6, 24, 2))
    buttons = []

    for i in range(0, len(hours), 4):
        row = [
            InlineKeyboardButton(f"{h}:00", callback_data=f"{setting_type}:{h}")
            for h in hours[i:i+4]
        ]
        buttons.append(row)

    buttons.append([InlineKeyboardButton("Back", callback_data="settings:back")])
    return InlineKeyboardMarkup(buttons)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)

    await update.message.reply_text(
        "Welcome to Water Reminder Bot!\n\n"
        "I'll help you stay hydrated by tracking your water intake "
        "and sending reminders.\n\n"
        "Commands:\n"
        "/drink - Log water (default 250ml)\n"
        "/today - View today's progress\n"
        "/history - View last 7 days\n"
        "/settings - Configure your preferences\n\n"
        "Let's start! Tap a button to log your first drink:",
        reply_markup=get_quick_drink_keyboard()
    )

    # Setup reminders for new user
    from scheduler import setup_user_reminder
    await setup_user_reminder(context, user_id)


async def drink_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /drink command."""
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)

    # Parse amount from arguments
    amount = 250
    if context.args:
        try:
            amount = int(context.args[0])
            if amount <= 0 or amount > 5000:
                await update.message.reply_text("Please enter an amount between 1 and 5000ml.")
                return
        except ValueError:
            await update.message.reply_text("Invalid amount. Usage: /drink [amount in ml]")
            return

    db.log_water(user_id, amount)
    total = db.get_today_total(user_id)
    goal = user["daily_goal_ml"]
    percentage = min(int(total / goal * 100), 100) if goal > 0 else 0

    bar = progress_bar(total, goal)

    message = f"Logged {amount}ml!\n\n"
    message += f"Today: {total}/{goal}ml {bar} {percentage}%"

    if total >= goal:
        message += "\n\nYou've reached your daily goal!"

    await update.message.reply_text(message, reply_markup=get_quick_drink_keyboard())


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command."""
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)

    total = db.get_today_total(user_id)
    goal = user["daily_goal_ml"]
    percentage = min(int(total / goal * 100), 100) if goal > 0 else 0

    bar = progress_bar(total, goal)

    message = f"Today's Progress\n\n"
    message += f"{total}/{goal}ml {bar} {percentage}%"

    if total >= goal:
        message += "\n\nYou've reached your daily goal!"
    else:
        remaining = goal - total
        message += f"\n\n{remaining}ml to go!"

    await update.message.reply_text(message, reply_markup=get_quick_drink_keyboard())


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history command."""
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)

    history = db.get_history(user_id, days=7)
    goal = user["daily_goal_ml"]

    message = "Last 7 Days\n\n"

    for entry in history:
        day_name = entry["date"].strftime("%a")
        total = entry["total"]

        if total >= goal:
            status = "+"
        elif total >= goal * 0.7:
            status = "~"
        elif total > 0:
            status = "-"
        else:
            status = " "

        message += f"{day_name}: {total}ml {status}\n"

    # Calculate weekly average
    week_total = sum(entry["total"] for entry in history)
    avg = week_total // len(history) if history else 0
    message += f"\nWeekly avg: {avg}ml/day"

    await update.message.reply_text(message)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command."""
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)

    await update.message.reply_text(
        "Settings",
        reply_markup=get_settings_keyboard(user)
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    data = query.data

    if data.startswith("drink:"):
        amount = int(data.split(":")[1])
        db.log_water(user_id, amount)

        total = db.get_today_total(user_id)
        goal = user["daily_goal_ml"]
        percentage = min(int(total / goal * 100), 100) if goal > 0 else 0

        bar = progress_bar(total, goal)

        message = f"Logged {amount}ml!\n\n"
        message += f"Today: {total}/{goal}ml {bar} {percentage}%"

        if total >= goal:
            message += "\n\nYou've reached your daily goal!"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "settings:goal":
        await query.edit_message_text(
            "Select your daily goal:",
            reply_markup=get_goal_keyboard()
        )

    elif data.startswith("goal:"):
        goal = int(data.split(":")[1])
        db.update_user_setting(user_id, "daily_goal_ml", goal)
        user = db.get_or_create_user(user_id)

        await query.edit_message_text(
            f"Daily goal set to {goal}ml!\n\nSettings",
            reply_markup=get_settings_keyboard(user)
        )

    elif data == "settings:interval":
        await query.edit_message_text(
            "Select reminder interval:",
            reply_markup=get_interval_keyboard()
        )

    elif data.startswith("interval:"):
        interval = int(data.split(":")[1])
        db.update_user_setting(user_id, "reminder_interval_hours", interval)
        user = db.get_or_create_user(user_id)

        # Reschedule reminders
        from scheduler import setup_user_reminder
        await setup_user_reminder(context, user_id)

        await query.edit_message_text(
            f"Reminder interval set to {interval} hours!\n\nSettings",
            reply_markup=get_settings_keyboard(user)
        )

    elif data == "settings:hours":
        await query.edit_message_text(
            "Select start hour for reminders:",
            reply_markup=get_hours_keyboard("start_hour")
        )

    elif data.startswith("start_hour:"):
        hour = int(data.split(":")[1])
        db.update_user_setting(user_id, "active_hours_start", hour)

        await query.edit_message_text(
            f"Start hour set to {hour}:00\n\nNow select end hour:",
            reply_markup=get_hours_keyboard("end_hour")
        )

    elif data.startswith("end_hour:"):
        hour = int(data.split(":")[1])
        db.update_user_setting(user_id, "active_hours_end", hour)
        user = db.get_or_create_user(user_id)

        # Reschedule reminders
        from scheduler import setup_user_reminder
        await setup_user_reminder(context, user_id)

        await query.edit_message_text(
            f"Active hours set to {user['active_hours_start']}:00-{hour}:00!\n\nSettings",
            reply_markup=get_settings_keyboard(user)
        )

    elif data == "settings:toggle_reminders":
        new_value = 0 if user["reminders_enabled"] else 1
        db.update_user_setting(user_id, "reminders_enabled", new_value)
        user = db.get_or_create_user(user_id)

        # Update reminders
        from scheduler import setup_user_reminder, remove_user_reminder
        if new_value:
            await setup_user_reminder(context, user_id)
        else:
            remove_user_reminder(context, user_id)

        status = "enabled" if new_value else "disabled"
        await query.edit_message_text(
            f"Reminders {status}!\n\nSettings",
            reply_markup=get_settings_keyboard(user)
        )

    elif data == "settings:menu":
        await query.edit_message_text(
            "Settings",
            reply_markup=get_settings_keyboard(user)
        )

    elif data == "menu:main":
        total = db.get_today_total(user_id)
        goal = user["daily_goal_ml"]
        percentage = min(int(total / goal * 100), 100) if goal > 0 else 0
        bar = progress_bar(total, goal)

        message = f"Today: {total}/{goal}ml {bar} {percentage}%"
        if total >= goal:
            message += "\n\nYou've reached your daily goal!"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "menu:today":
        total = db.get_today_total(user_id)
        goal = user["daily_goal_ml"]
        percentage = min(int(total / goal * 100), 100) if goal > 0 else 0
        bar = progress_bar(total, goal)

        message = f"Today's Progress\n\n{total}/{goal}ml {bar} {percentage}%"
        if total >= goal:
            message += "\n\nYou've reached your daily goal!"
        else:
            remaining = goal - total
            message += f"\n\n{remaining}ml to go!"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "adjust:undo":
        amount = db.undo_last_drink(user_id)
        total = db.get_today_total(user_id)
        goal = user["daily_goal_ml"]
        percentage = min(int(total / goal * 100), 100) if goal > 0 else 0
        bar = progress_bar(total, goal)

        if amount > 0:
            message = f"Removed {amount}ml\n\n"
        else:
            message = "Nothing to undo\n\n"
        message += f"Today: {total}/{goal}ml {bar} {percentage}%"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "adjust:reset_confirm":
        await query.edit_message_text(
            "Reset today's progress to 0?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Yes, reset", callback_data="adjust:reset"),
                    InlineKeyboardButton("Cancel", callback_data="menu:main"),
                ]
            ])
        )

    elif data == "adjust:reset":
        deleted = db.clear_today(user_id)
        total = db.get_today_total(user_id)
        goal = user["daily_goal_ml"]
        bar = progress_bar(total, goal)

        message = f"Progress reset ({deleted} entries removed)\n\n"
        message += f"Today: {total}/{goal}ml {bar} 0%"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "menu:history":
        history = db.get_history(user_id, days=7)
        goal = user["daily_goal_ml"]

        message = "Last 7 Days\n\n"
        for entry in history:
            day_name = entry["date"].strftime("%a")
            total = entry["total"]
            if total >= goal:
                status = "+"
            elif total >= goal * 0.7:
                status = "~"
            elif total > 0:
                status = "-"
            else:
                status = " "
            message += f"{day_name}: {total}ml {status}\n"

        week_total = sum(entry["total"] for entry in history)
        avg = week_total // len(history) if history else 0
        message += f"\nWeekly avg: {avg}ml/day"

        await query.edit_message_text(message, reply_markup=get_quick_drink_keyboard())

    elif data == "settings:back":
        await query.edit_message_text(
            "Settings",
            reply_markup=get_settings_keyboard(user)
        )
