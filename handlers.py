from datetime import date

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
            InlineKeyboardButton("Routines", callback_data="routines:menu"),
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
    buttons.append([InlineKeyboardButton("History", callback_data="pills:history")])
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


def get_routines_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Get routines menu keyboard listing user's routines."""
    routines = db.get_user_routines(user_id)
    today_logs = db.get_today_routine_item_logs(user_id)
    taken_ids = {log["routine_item_id"] for log in today_logs}

    buttons = []
    for r in routines:
        due_items = [i for i in r["items"] if i["due_today"]]
        taken_count = sum(1 for i in due_items if i["id"] in taken_ids)
        total_due = len(due_items)
        time_str = f"{r['remind_at_hour']:02d}:{r['remind_at_minute']:02d}"
        label = f"{r['name']} — {time_str} — {taken_count}/{total_due} done"
        buttons.append([InlineKeyboardButton(label, callback_data=f"routine_view:{r['id']}")])

    buttons.append([InlineKeyboardButton("Add routine", callback_data="routine_add")])
    buttons.append([InlineKeyboardButton("History", callback_data="routines:history")])
    buttons.append([InlineKeyboardButton("Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def get_routine_view_keyboard(routine_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for viewing a single routine with its items."""
    routine = db.get_routine(routine_id)
    if not routine:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Back", callback_data="routines:menu")]
        ])

    today_logs = db.get_today_routine_item_logs(user_id)
    taken_ids = {log["routine_item_id"] for log in today_logs}

    buttons = []
    for item in routine["items"]:
        if not item["due_today"]:
            status = "·"
        elif item["id"] in taken_ids:
            status = "+"
        else:
            status = "-"
        emoji = "🧴" if item["type"] == "cream" else "💊"
        period_label = {1: "daily", 2: "every 2 days", 3: "every 3 days", 7: "weekly"}.get(
            item["period_days"], f"every {item['period_days']} days"
        )
        label = f"[{status}] {emoji} {item['name']} — {period_label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"routine_item_view:{item['id']}")])

    buttons.append([
        InlineKeyboardButton("Add cream", callback_data=f"routine_add_cream:{routine_id}"),
        InlineKeyboardButton("Add pill", callback_data=f"routine_add_pill:{routine_id}"),
    ])
    buttons.append([
        InlineKeyboardButton("Edit time", callback_data=f"routine_edit_time:{routine_id}"),
        InlineKeyboardButton("Delete routine", callback_data=f"routine_delete_confirm:{routine_id}"),
    ])
    buttons.append([InlineKeyboardButton("Back", callback_data="routines:menu")])
    return InlineKeyboardMarkup(buttons)


def get_period_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing an item's period."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Every day", callback_data="routine_period:1"),
            InlineKeyboardButton("Every 2 days", callback_data="routine_period:2"),
        ],
        [
            InlineKeyboardButton("Every 3 days", callback_data="routine_period:3"),
            InlineKeyboardButton("Weekly", callback_data="routine_period:7"),
        ],
        [InlineKeyboardButton("Cancel", callback_data="routines:menu")],
    ])


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

    elif data == "pills:history":
        history = db.get_pill_history(user_id, days=7)
        if not history:
            await query.edit_message_text(
                "No pills added yet.",
                reply_markup=get_pills_keyboard(user_id)
            )
            return

        message = "Pills — Last 7 Days\n\n"
        for entry in history:
            day_name = entry["date"].strftime("%a")
            statuses = " ".join(
                f"[+]{p['name']}" if p["taken"] else f"[-]{p['name']}"
                for p in entry["pills"]
            )
            message += f"{day_name}: {statuses}\n"

        await query.edit_message_text(message, reply_markup=get_pills_keyboard(user_id))

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

        from scheduler import cancel_pill_followup
        cancel_pill_followup(context, pill_id)

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

    elif data == "routines:menu":
        await query.edit_message_text(
            "Your routines:",
            reply_markup=get_routines_keyboard(user_id)
        )

    elif data == "routines:history":
        history = db.get_routine_history(user_id, days=7)
        if not history or not any(day["routines"] for day in history):
            await query.edit_message_text(
                "No routine activity yet.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return

        lines = ["Routines — Last 7 Days", ""]
        for entry in history:
            day_name = entry["date"].strftime("%a %b %d")
            if not entry["routines"]:
                lines.append(day_name)
                lines.append("  (nothing scheduled)")
            else:
                lines.append(day_name)
                for r in entry["routines"]:
                    items_str = " ".join(
                        f"[+]{i['name']}" if i["taken"] else f"[-]{i['name']}"
                        for i in r["items"]
                    )
                    lines.append(f"  {r['name']}: {items_str}")
            lines.append("")

        await query.edit_message_text(
            "\n".join(lines).rstrip(),
            reply_markup=get_routines_keyboard(user_id)
        )

    elif data == "routine_add":
        context.user_data["awaiting_routine_name"] = True
        await query.edit_message_text(
            "Enter the routine name (e.g., 'Morning face'):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="routines:menu")]
            ])
        )

    elif data.startswith("routine_new_time:"):
        hour = int(data.split(":")[1])
        pending_name = context.user_data.pop("pending_routine_name", None)
        if not pending_name:
            await query.edit_message_text(
                "Routine creation expired. Try again.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        routine_id = db.add_routine(user_id, pending_name, hour, 0)

        from scheduler import setup_routine_reminder
        setup_routine_reminder(
            context, routine_id, user_id, hour, 0,
            user.get("timezone", "UTC")
        )

        routine = db.get_routine(routine_id)
        time_str = f"{routine['remind_at_hour']:02d}:{routine['remind_at_minute']:02d}"
        msg = f"{routine['name']} — {time_str}\n\nNo items yet. Add creams or pills:"
        await query.edit_message_text(
            msg,
            reply_markup=get_routine_view_keyboard(routine_id, user_id)
        )

    elif data.startswith("routine_view:"):
        routine_id = int(data.split(":")[1])
        routine = db.get_routine(routine_id)
        if not routine:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        time_str = f"{routine['remind_at_hour']:02d}:{routine['remind_at_minute']:02d}"
        if not routine["items"]:
            body = "No items yet. Add creams or pills:"
        else:
            body = "[+] taken today  [-] due but not taken  [·] not due today"
        msg = f"{routine['name']} — {time_str}\n\n{body}"
        await query.edit_message_text(
            msg,
            reply_markup=get_routine_view_keyboard(routine_id, user_id)
        )

    elif data.startswith("routine_add_cream:"):
        routine_id = int(data.split(":")[1])
        context.user_data["awaiting_routine_item"] = {"routine_id": routine_id, "type": "cream"}
        await query.edit_message_text(
            "Enter the cream name:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data=f"routine_view:{routine_id}")]
            ])
        )

    elif data.startswith("routine_add_pill:"):
        routine_id = int(data.split(":")[1])
        context.user_data["awaiting_routine_item"] = {"routine_id": routine_id, "type": "pill"}
        await query.edit_message_text(
            "Enter the pill name:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data=f"routine_view:{routine_id}")]
            ])
        )

    elif data.startswith("routine_period:"):
        period_days = int(data.split(":")[1])
        pending = context.user_data.pop("pending_item", None)
        if not pending:
            await query.edit_message_text(
                "Item creation expired. Try again.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        db.add_routine_item(
            pending["routine_id"],
            pending["type"],
            pending["name"],
            period_days,
            date.today(),
        )
        routine = db.get_routine(pending["routine_id"])
        time_str = f"{routine['remind_at_hour']:02d}:{routine['remind_at_minute']:02d}"
        msg = (
            f"Added {pending['name']} to {routine['name']}.\n\n"
            f"{routine['name']} — {time_str}"
        )
        await query.edit_message_text(
            msg,
            reply_markup=get_routine_view_keyboard(pending["routine_id"], user_id)
        )

    elif data.startswith("routine_item_view:"):
        item_id = int(data.split(":")[1])
        item = db.get_routine_item(item_id)
        if not item:
            await query.edit_message_text(
                "Item not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        period_label = {1: "every day", 2: "every 2 days", 3: "every 3 days", 7: "weekly"}.get(
            item["period_days"], f"every {item['period_days']} days"
        )
        emoji = "🧴" if item["type"] == "cream" else "💊"
        msg = (
            f"{emoji} {item['name']}\n\n"
            f"Period: {period_label}\n"
            f"Started: {item['start_date'].isoformat()}"
        )
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Delete", callback_data=f"routine_item_delete:{item_id}")],
                [InlineKeyboardButton("Back", callback_data=f"routine_view:{item['routine_id']}")],
            ])
        )

    elif data.startswith("routine_item_delete:"):
        item_id = int(data.split(":")[1])
        item = db.get_routine_item(item_id)
        if not item:
            await query.edit_message_text(
                "Item not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        routine_id = item["routine_id"]
        db.delete_routine_item(item_id)
        await query.edit_message_text(
            f"Deleted {item['name']}.",
            reply_markup=get_routine_view_keyboard(routine_id, user_id)
        )

    elif data.startswith("routine_item_taken:"):
        item_id = int(data.split(":")[1])
        item = db.get_routine_item(item_id)
        if not item:
            await query.edit_message_text(
                "Item not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return

        today_logs = db.get_today_routine_item_logs(user_id)
        already = any(log["routine_item_id"] == item_id for log in today_logs)
        if not already:
            db.log_routine_item_taken(item_id, user_id)

        from scheduler import cancel_routine_followup
        routine = db.get_routine(item["routine_id"])
        today_logs_after = db.get_today_routine_item_logs(user_id)
        taken_ids = {log["routine_item_id"] for log in today_logs_after}
        still_due = [
            i for i in routine["items"]
            if i["due_today"] and i["id"] not in taken_ids
        ]
        if not still_due:
            cancel_routine_followup(context, item["routine_id"])

        await query.edit_message_text(
            f"Logged {item['name']} as taken!",
            reply_markup=get_routine_view_keyboard(item["routine_id"], user_id)
        )

    elif data.startswith("routine_edit_time:"):
        routine_id = int(data.split(":")[1])
        await query.edit_message_text(
            "Select reminder hour:",
            reply_markup=get_hour_picker_keyboard(f"routine_time:{routine_id}")
        )

    elif data.startswith("routine_time:"):
        parts = data.split(":")
        routine_id = int(parts[1])
        hour = int(parts[2])
        routine = db.get_routine(routine_id)
        if not routine:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        db.update_routine_time(routine_id, hour, 0)

        from scheduler import setup_routine_reminder
        setup_routine_reminder(
            context, routine_id, user_id, hour, 0,
            user.get("timezone", "UTC")
        )

        await query.edit_message_text(
            f"Time updated to {hour:02d}:00",
            reply_markup=get_routine_view_keyboard(routine_id, user_id)
        )

    elif data.startswith("routine_delete_confirm:"):
        routine_id = int(data.split(":")[1])
        routine = db.get_routine(routine_id)
        if not routine:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        await query.edit_message_text(
            f"Delete {routine['name']} and all its items?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Yes, delete", callback_data=f"routine_delete:{routine_id}"),
                    InlineKeyboardButton("Cancel", callback_data=f"routine_view:{routine_id}"),
                ]
            ])
        )

    elif data.startswith("routine_delete:"):
        routine_id = int(data.split(":")[1])
        from scheduler import remove_routine_reminder
        remove_routine_reminder(context, routine_id)
        db.delete_routine(routine_id)
        await query.edit_message_text(
            "Routine deleted.",
            reply_markup=get_routines_keyboard(user_id)
        )

    elif data == "settings:back":
        await query.edit_message_text(
            "Settings",
            reply_markup=get_settings_keyboard(user)
        )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free text messages (used for pill/routine name input)."""
    user_id = update.effective_user.id

    if context.user_data.get("awaiting_pill_name"):
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
        return

    if context.user_data.get("awaiting_routine_name"):
        routine_name = update.message.text.strip()
        if not routine_name or len(routine_name) > 50:
            await update.message.reply_text("Please enter a valid routine name (1-50 characters).")
            return
        context.user_data["awaiting_routine_name"] = False
        context.user_data["pending_routine_name"] = routine_name
        await update.message.reply_text(
            f"Routine name: {routine_name}\n\nSelect reminder hour:",
            reply_markup=get_hour_picker_keyboard("routine_new_time")
        )
        return

    pending_item = context.user_data.get("awaiting_routine_item")
    if pending_item:
        item_name = update.message.text.strip()
        if not item_name or len(item_name) > 50:
            await update.message.reply_text("Please enter a valid name (1-50 characters).")
            return
        context.user_data.pop("awaiting_routine_item", None)
        context.user_data["pending_item"] = {
            "routine_id": pending_item["routine_id"],
            "type": pending_item["type"],
            "name": item_name,
        }
        await update.message.reply_text(
            f"{item_name} — how often?",
            reply_markup=get_period_keyboard()
        )
        return
