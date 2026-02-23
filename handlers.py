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
            InlineKeyboardButton("+100", callback_data="drink:100"),
            InlineKeyboardButton("+300", callback_data="drink:300"),
            InlineKeyboardButton("+500", callback_data="drink:500"),
        ],
        [
            InlineKeyboardButton("Undo", callback_data="adjust:undo"),
            InlineKeyboardButton("Reset", callback_data="adjust:reset_confirm"),
        ],
        [
            InlineKeyboardButton("Today", callback_data="menu:today"),
            InlineKeyboardButton("History", callback_data="menu:history"),
            InlineKeyboardButton("Settings", callback_data="settings:menu"),
        ],
        [
            InlineKeyboardButton("Pills", callback_data="pills:menu"),
        ]
    ])


def get_settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    """Get settings menu keyboard."""
    reminders_status = "ON" if user["reminders_enabled"] else "OFF"
    timezone = user.get("timezone", "UTC")

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
            f"Timezone: {timezone}",
            callback_data="settings:timezone"
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


def get_timezone_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    """Get timezone selection keyboard."""
    timezones = [
        ("UTC", "UTC"),
        ("London", "Europe/London"),
        ("Paris", "Europe/Paris"),
        ("Berlin", "Europe/Berlin"),
        ("Kyiv", "Europe/Kyiv"),
        ("Moscow", "Europe/Moscow"),
        ("Dubai", "Asia/Dubai"),
        ("Mumbai", "Asia/Kolkata"),
        ("Bangkok", "Asia/Bangkok"),
        ("Singapore", "Asia/Singapore"),
        ("Tokyo", "Asia/Tokyo"),
        ("Sydney", "Australia/Sydney"),
        ("New York", "America/New_York"),
        ("Chicago", "America/Chicago"),
        ("Denver", "America/Denver"),
        ("Los Angeles", "America/Los_Angeles"),
    ]

    per_page = 8
    start = page * per_page
    end = start + per_page
    page_timezones = timezones[start:end]

    buttons = []
    for i in range(0, len(page_timezones), 2):
        row = [
            InlineKeyboardButton(tz[0], callback_data=f"tz:{tz[1]}")
            for tz in page_timezones[i:i+2]
        ]
        buttons.append(row)

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("<", callback_data=f"tz_page:{page-1}"))
    if end < len(timezones):
        nav_row.append(InlineKeyboardButton(">", callback_data=f"tz_page:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("Back", callback_data="settings:back")])
    return InlineKeyboardMarkup(buttons)


def get_pills_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Get pills menu keyboard showing today's status."""
    pills = db.get_user_pills(user_id)
    today_logs = db.get_today_pill_logs(user_id)
    taken_pill_ids = {log["pill_id"] for log in today_logs}

    buttons = []
    for pill in pills:
        times = ", ".join(f"{r['remind_at_hour']:02d}:{r['remind_at_minute']:02d}" for r in pill["reminders"])
        check = "+" if pill["id"] in taken_pill_ids else "-"
        label = f"[{check}] {pill['name']}"
        if times:
            label += f" — {times}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"pill_view:{pill['id']}")])

    buttons.append([InlineKeyboardButton("Add pill", callback_data="pill_add")])
    buttons.append([InlineKeyboardButton("Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def get_pill_view_keyboard(pill_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for viewing/managing a single pill."""
    pill = db.get_pill(pill_id)
    today_logs = db.get_today_pill_logs(user_id)
    taken = any(log["pill_id"] == pill_id for log in today_logs)

    buttons = []
    if not taken:
        buttons.append([InlineKeyboardButton(f"Take {pill['name']}", callback_data=f"pill_taken:{pill_id}")])

    buttons.append([InlineKeyboardButton("Add reminder time", callback_data=f"pill_add_time:{pill_id}")])
    buttons.append([InlineKeyboardButton("Delete pill", callback_data=f"pill_delete_confirm:{pill_id}")])
    buttons.append([InlineKeyboardButton("Back", callback_data="pills:menu")])
    return InlineKeyboardMarkup(buttons)


def get_hour_picker_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """Get hour picker keyboard for pill reminders."""
    buttons = []
    for row_start in range(0, 24, 4):
        row = [
            InlineKeyboardButton(f"{h:02d}:00", callback_data=f"{callback_prefix}:{h}")
            for h in range(row_start, min(row_start + 4, 24))
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Cancel", callback_data="pills:menu")])
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
    amount = 300
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

    elif data == "settings:timezone":
        await query.edit_message_text(
            "Select your timezone:",
            reply_markup=get_timezone_keyboard(0)
        )

    elif data.startswith("tz_page:"):
        page = int(data.split(":")[1])
        await query.edit_message_text(
            "Select your timezone:",
            reply_markup=get_timezone_keyboard(page)
        )

    elif data.startswith("tz:"):
        timezone = data.split(":", 1)[1]
        db.update_user_setting(user_id, "timezone", timezone)
        user = db.get_or_create_user(user_id)

        await query.edit_message_text(
            f"Timezone set to {timezone}!\n\nSettings",
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

    elif data == "pills:menu":
        await query.edit_message_text(
            "Your pills:",
            reply_markup=get_pills_keyboard(user_id)
        )

    elif data == "pill_add":
        context.user_data["awaiting_pill_name"] = True
        await query.edit_message_text(
            "Enter the pill name:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="pills:menu")]
            ])
        )

    elif data.startswith("pill_view:"):
        pill_id = int(data.split(":")[1])
        pill = db.get_pill(pill_id)
        if not pill:
            await query.edit_message_text("Pill not found.", reply_markup=get_pills_keyboard(user_id))
            return

        times = ", ".join(f"{r['remind_at_hour']:02d}:{r['remind_at_minute']:02d}" for r in pill["reminders"])
        today_logs = db.get_today_pill_logs(user_id)
        taken = any(log["pill_id"] == pill_id for log in today_logs)
        status = "Taken today" if taken else "Not taken yet"

        msg = f"{pill['name']}\n\nReminders: {times or 'none'}\nStatus: {status}"
        await query.edit_message_text(msg, reply_markup=get_pill_view_keyboard(pill_id, user_id))

    elif data.startswith("pill_taken:"):
        pill_id = int(data.split(":")[1])
        pill = db.get_pill(pill_id)
        if not pill:
            await query.edit_message_text("Pill not found.", reply_markup=get_pills_keyboard(user_id))
            return
        db.log_pill_taken(pill_id, user_id)
        await query.edit_message_text(
            f"Logged {pill['name']} as taken!",
            reply_markup=get_pills_keyboard(user_id)
        )

    elif data.startswith("pill_add_time:"):
        pill_id = int(data.split(":")[1])
        await query.edit_message_text(
            "Select reminder hour:",
            reply_markup=get_hour_picker_keyboard(f"pill_time:{pill_id}")
        )

    elif data.startswith("pill_time:"):
        # Format: pill_time:<pill_id>:<hour>
        parts = data.split(":")
        pill_id = int(parts[1])
        hour = int(parts[2])
        pill = db.get_pill(pill_id)
        if not pill:
            await query.edit_message_text("Pill not found.", reply_markup=get_pills_keyboard(user_id))
            return

        db.add_pill_reminder(pill_id, hour, 0)

        from scheduler import setup_pill_reminder
        setup_pill_reminder(context, pill_id, pill["name"], user_id, hour, 0, user.get("timezone", "UTC"))

        await query.edit_message_text(
            f"Reminder added: {pill['name']} at {hour:02d}:00",
            reply_markup=get_pill_view_keyboard(pill_id, user_id)
        )

    elif data.startswith("pill_delete_confirm:"):
        pill_id = int(data.split(":")[1])
        pill = db.get_pill(pill_id)
        if not pill:
            await query.edit_message_text("Pill not found.", reply_markup=get_pills_keyboard(user_id))
            return
        await query.edit_message_text(
            f"Delete {pill['name']}?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Yes, delete", callback_data=f"pill_delete:{pill_id}"),
                    InlineKeyboardButton("Cancel", callback_data=f"pill_view:{pill_id}"),
                ]
            ])
        )

    elif data.startswith("pill_delete:"):
        pill_id = int(data.split(":")[1])
        pill = db.get_pill(pill_id)
        if pill:
            from scheduler import remove_pill_reminders
            remove_pill_reminders(context, pill_id)
            db.delete_pill(pill_id)
        await query.edit_message_text(
            "Pill deleted.",
            reply_markup=get_pills_keyboard(user_id)
        )

    elif data == "settings:back":
        await query.edit_message_text(
            "Settings",
            reply_markup=get_settings_keyboard(user)
        )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free text messages (used for pill name input)."""
    if not context.user_data.get("awaiting_pill_name"):
        return

    user_id = update.effective_user.id
    pill_name = update.message.text.strip()

    if not pill_name or len(pill_name) > 50:
        await update.message.reply_text("Please enter a valid pill name (1-50 characters).")
        return

    context.user_data["awaiting_pill_name"] = False

    pill_id = db.add_pill(user_id, pill_name)

    await update.message.reply_text(
        f"Added {pill_name}! Now add a reminder time:",
        reply_markup=get_hour_picker_keyboard(f"pill_time:{pill_id}")
    )
