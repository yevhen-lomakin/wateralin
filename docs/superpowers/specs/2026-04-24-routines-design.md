# Routines — Design

Add **routines** to the Telegram water/pill bot: time-based groupings of cream and pill items, each item with its own repetition period (every N days). At the routine's time, the bot sends one reminder listing all items due that day, and re-sends every 30 minutes until each due item is marked taken.

This is additive. The existing standalone pill feature (a pill with its own reminder times, independent of routines) is untouched.

## Core concepts

- **Routine** — a user-owned, named time slot. Fires once per day at a fixed hour:minute in the user's timezone. Holds multiple items.
- **Routine item** — a cream or a pill belonging to a routine. Has a name, a `period_days` (1, 2, 3, or 7), and a `start_date` that anchors the repetition.
- **Due today** — an item is due today if `(today - start_date).days % period_days == 0`. Today is evaluated in the user's timezone on the day the routine fires.
- **Taken today** — an item is taken today if there's a row in `routine_item_logs` with `DATE(applied_at) = today`.
- **Follow-up** — while any items in a routine are due-but-not-taken today, the bot re-sends the reminder every 30 minutes. Follow-up stops once all due items for that routine are marked taken.

## Data model

Three new tables, created in `database.py:init_db()`:

```sql
CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    remind_at_hour INTEGER NOT NULL,
    remind_at_minute INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS routine_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('cream', 'pill')),
    name TEXT NOT NULL,
    period_days INTEGER NOT NULL DEFAULT 1,
    start_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (routine_id) REFERENCES routines (id)
);

CREATE TABLE IF NOT EXISTS routine_item_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_item_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (routine_item_id) REFERENCES routine_items (id),
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE INDEX IF NOT EXISTS idx_routine_item_logs_user_date
    ON routine_item_logs (user_id, applied_at);
```

Notes:

- `start_date` is set to `date.today()` (in user's timezone) when the item is added.
- `type` is stored in the item itself because it's cosmetic only — it controls the emoji (🧴 for cream, 💊 for pill) and the verb in reminder messages ("apply" vs "take"). All scheduling and period logic is identical.
- Existing `pills` / `pill_reminders` / `pill_logs` tables and all existing code paths stay untouched.

## Database functions

Added to `database.py`:

- `add_routine(user_id, name, hour, minute) -> int` (returns routine id)
- `get_user_routines(user_id) -> list[dict]` — each routine includes its `items` list; each item includes a derived `due_today: bool` flag
- `get_routine(routine_id) -> dict | None` — same shape as above, single routine
- `delete_routine(routine_id)` — cascades to items and logs
- `add_routine_item(routine_id, type, name, period_days, start_date) -> int`
- `get_routine_item(item_id) -> dict | None`
- `delete_routine_item(item_id)` — cascades to logs
- `log_routine_item_taken(item_id, user_id)`
- `get_today_routine_item_logs(user_id) -> list[dict]` — used for "taken today?" checks
- `get_routine_history(user_id, days=7) -> list[dict]` — per-day: `{date, routines: [{name, items: [{name, type, taken, due}]}]}`. Only includes items that were due on that day.
- `get_all_routines_for_scheduler() -> list[dict]` — for startup restore, one row per routine with `user_id`, `routine_id`, `name`, `hour`, `minute`

Helper (module-level, not a public API):

- `_is_item_due_on(start_date, period_days, on_date) -> bool` — `(on_date - start_date).days % period_days == 0`

## Scheduler

Added to `scheduler.py`. Mirrors the pill reminder structure.

Job names:

- `routine_{routine_id}` — the daily run_daily job
- `routine_followup_{routine_id}` — the repeating 30-min follow-up

Functions:

- `send_routine_reminder(context)` — the daily callback. Loads the routine, checks due/not-taken items in the user's timezone, and either:
  - Does nothing if no items are due today.
  - Sends a message with one `Taken: {name}` button per due-and-not-taken item, then schedules the follow-up.
- `send_routine_followup(context)` — the 30-min callback. Same check; if any due-and-not-taken items remain, resends the reminder with the current remaining buttons; otherwise cancels itself.
- `schedule_routine_followup(context, routine_id, user_id)` — creates/replaces the follow-up job.
- `cancel_routine_followup(context, routine_id)` — removes the follow-up job.
- `setup_routine_reminder(context, routine_id, name, user_id, hour, minute, timezone)` — creates/replaces the `run_daily` job.
- `remove_routine_reminder(context, routine_id)` — removes both the daily and follow-up jobs.
- `restore_all_routine_reminders(context)` — iterates `get_all_routines_for_scheduler()` and re-registers jobs on startup.

Reminder message format:

```
🧴💊 {routine_name} — time to apply/take!
```

With one button per due-and-not-taken item labeled `Taken: {item_name}`.

## Handlers and UI

Added to `handlers.py`. No new commands — everything is button-driven from the main menu.

### Main menu

Add a `Routines` button to `get_quick_drink_keyboard()` (same row as `Pills` or a new row).

### Keyboards

- `get_routines_keyboard(user_id)` — list user's routines with "name — HH:MM — X/Y due today" labels, plus `[Add routine]`, `[History]`, `[Back]`.
- `get_routine_view_keyboard(routine_id, user_id)` — shows each item as a button labeled with status marker, `[Add cream]`, `[Add pill]`, `[Edit time]`, `[Delete routine]`, `[Back]`.
- `get_period_keyboard(callback_prefix)` — four buttons: `Every day` → `:1`, `Every 2 days` → `:2`, `Every 3 days` → `:3`, `Weekly` → `:7`, plus `[Cancel]`.
- Reuse `get_hour_picker_keyboard` from the pill feature for routine time selection.

### Callback routes

All added to `button_callback()`:

- `routines:menu` — show routines list
- `routines:history` — show 7-day history
- `routine_add` — prompt for routine name (sets `awaiting_routine_name = True` in `context.user_data`)
- `routine_view:<id>` — show routine detail
- `routine_add_cream:<id>` — prompt for cream name (sets `awaiting_routine_item = {routine_id, type: 'cream'}`)
- `routine_add_pill:<id>` — prompt for pill name (sets `awaiting_routine_item = {routine_id, type: 'pill'}`)
- `routine_period:<days>` — read `routine_id`, `type`, `name` from `context.user_data['pending_item']`, create the item with `start_date = today-in-user-tz`, clear pending state, show routine view
- `routine_item_view:<item_id>` — show item detail with delete button
- `routine_item_delete:<item_id>` — delete item, return to routine view
- `routine_item_taken:<item_id>` — log taken, re-check follow-up, refresh message
- `routine_edit_time:<id>` — open hour picker
- `routine_time:<id>:<hour>` — save new time, reschedule daily job
- `routine_delete_confirm:<id>` — confirmation prompt
- `routine_delete:<id>` — delete routine, remove jobs, return to routines menu

### Text handler

Extend `text_message_handler()` to handle three states:

- `awaiting_pill_name` (existing, unchanged)
- `awaiting_routine_name` — on receipt of the name, store it in `context.user_data['pending_routine_name']`, then prompt for hour using `get_hour_picker_keyboard` with the prefix `routine_new_time`. On hour callback `routine_new_time:<hour>`, create the routine with that name and time, schedule the daily job, clear pending state, show the routine view.
- `awaiting_routine_item` (dict `{routine_id, type}`) — on receipt of the name, promote the pending state to `context.user_data['pending_item'] = {routine_id, type, name}`, clear `awaiting_routine_item`, then present `get_period_keyboard`. The `routine_period:<days>` callback reads `pending_item` from `user_data`, creates the row, clears the state, shows the routine view.

### Bot startup

In `bot.py:post_init()`, add `await restore_all_routine_reminders(application)` alongside the existing two restore calls.

## History view

Route `routines:history` produces output like:

```
Routines — Last 7 Days

Thu Apr 24
  Morning face: [+]Retinol [+]Vit C
  Evening body: [+]Moisturizer [-]Night cream

Wed Apr 23
  Morning face: [+]Vit C
  Evening body: [+]Moisturizer [+]Night cream

Tue Apr 22
  (nothing scheduled)
```

Rules:

- For each of the last 7 days, for each of the user's routines, list items that were **due** that day.
- `[+]` if there's a log for that item on that date, `[-]` if not.
- If no routine had any due items on a given day, show `(nothing scheduled)`.
- A routine with no due items on a given day is simply omitted for that day (don't print an empty line).

## Reminder lifecycle (end-to-end)

1. User creates routine "Morning face" at 08:00.
2. User adds cream "Retinol" period=2, pill "Vit D" period=1. `start_date = 2026-04-24` for both.
3. `scheduler.setup_routine_reminder` registers a `run_daily` job at 08:00 in user's timezone.
4. On 2026-04-24 at 08:00, job fires. Both items are due (day 0). Neither is taken. Message sent with two buttons. Follow-up scheduled.
5. User taps `Taken: Vit D`. Log written. `send_routine_followup` re-check next cycle: Retinol still due-and-not-taken → resend with only the Retinol button. Vit D now excluded.
6. User taps `Taken: Retinol`. Log written. Next follow-up tick finds nothing due-and-not-taken → cancels itself.
7. On 2026-04-25 at 08:00, only Vit D is due (Retinol is day 1 of period 2 → not due). If user doesn't tap, follow-up only lists Vit D.

## Timezone handling

- Use the same pattern as existing pill reminders: `ZoneInfo(user.get("timezone", "UTC"))`, fall back to UTC on exception.
- "Today" for due-check and taken-check is derived from `datetime.now(user_tz).date()`.
- `run_daily` already accepts a `tz`-aware `time` object — same as `setup_pill_reminder`.

## Non-goals for v1

- Editing item names or periods (delete + re-add instead).
- Editing a routine's name (delete + re-add instead; time editing is supported).
- Per-item history on a detail screen (only the aggregated 7-day history).
- Pausing routines (only delete).
- Multiple fire times per routine (create a second routine).
- Sharing a cream/pill definition across routines.
- Custom period values beyond 1, 2, 3, 7.
- Migration of existing standalone pills into routines.

## Files changed

- `database.py` — new tables in `init_db`, new functions listed above.
- `handlers.py` — new keyboards, new callback branches, extended `text_message_handler`, new button in `get_quick_drink_keyboard`.
- `scheduler.py` — new reminder/follow-up/setup/restore functions.
- `bot.py` — one line in `post_init` to restore routine reminders.
