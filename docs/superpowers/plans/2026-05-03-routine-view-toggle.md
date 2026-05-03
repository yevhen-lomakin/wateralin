# Routine View Direct-Tap Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users mark routine items taken / undo from the routine view (Routines → tap a routine), not just from the daily reminder message.

**Architecture:** The routine-view keyboard already renders one button per item with a status marker. Today every button routes to the item detail screen. We change the route to depend on the item's state: tap `[-]` to take, `[+]` to undo, `[·]` to open detail. We also collapse the post-tap message back to the routine view body (header + legend) so toggling stays visually quiet, and add a new `routine_item_untake:<id>` callback that deletes today's log and re-arms the follow-up reminder if the item is still due today and the daily fire-time has already passed.

**Tech Stack:** Python, python-telegram-bot v20+, SQLite, zoneinfo. (Repo has no test framework — verify each task by running the bot and exercising the UI in Telegram, matching the existing routines plan's convention.)

**Spec reference:** `docs/superpowers/specs/2026-05-03-routine-view-toggle-design.md`

---

## File Structure

- **Modify** `database.py` — add `delete_today_routine_item_log(item_id, user_id, today=None)`.
- **Modify** `handlers.py` — extract a small `_render_routine_view_message(routine_id, user_id)` helper that returns `(text, keyboard)`; update `get_routine_view_keyboard` so item-row buttons route by item state; update the `routine_view:` and `routine_item_taken:` callback branches to use the helper; add a new `routine_item_untake:<id>` branch that deletes today's log and conditionally re-arms the routine follow-up.
- **Untouched:** `scheduler.py`, `bot.py`, `database.py` schema. The existing `scheduler.schedule_routine_followup` is reused as-is.

Each task produces a standalone commit that leaves the bot runnable.

---

## Task 1: Add `delete_today_routine_item_log` to database.py

**Files:**
- Modify: `database.py`

- [ ] **Step 1: Add the new function**

Open `database.py`. Append the following function at the end of the `# --- Routine functions ---` block (just after `get_all_routines_for_scheduler`, around line 663):

```python
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
```

`Optional` and `date` are already imported at the top of the file (lines 3-4).

- [ ] **Step 2: Smoke-check the import**

Run: `python -c "import database; print(database.delete_today_routine_item_log.__doc__)"`
Expected: prints the docstring's first line, no exception.

- [ ] **Step 3: Commit**

```bash
git add database.py
git commit -m "feat: delete_today_routine_item_log helper for untake"
```

---

## Task 2: Extract routine-view renderer + adopt new legend

**Files:**
- Modify: `handlers.py`

This task introduces a helper that renders the routine-view message body+keyboard, switches `routine_view:` to use it, and changes the legend wording. It does **not** yet change tap routing — that comes in Task 3 — so item-row taps still go to the detail screen at the end of this task.

- [ ] **Step 1: Add the renderer helper**

Open `handlers.py`. Immediately above `async def start_command` (around line 289, just after `get_period_keyboard`), add:

```python
def _render_routine_view_message(routine_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    """Build (text, keyboard) for the routine view screen. Returns None if the routine is missing."""
    routine = db.get_routine(routine_id)
    if not routine:
        return None
    time_str = f"{routine['remind_at_hour']:02d}:{routine['remind_at_minute']:02d}"
    if not routine["items"]:
        body = "No items yet. Add creams or pills:"
    else:
        body = "[+] taken — tap to undo  [-] tap to take  [·] not due — tap to manage"
    text = f"{routine['name']} — {time_str}\n\n{body}"
    return text, get_routine_view_keyboard(routine_id, user_id)
```

Note: `tuple[str, InlineKeyboardMarkup] | None` requires Python 3.10+. The existing code uses 3.10+ syntax (`list[dict]` in scheduler.py:282) so this is consistent.

- [ ] **Step 2: Use the helper in the `routine_view:` callback branch**

In `handlers.py`, find the `routine_view:` branch (currently around lines 830-848):

```python
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
```

Replace it with:

```python
    elif data.startswith("routine_view:"):
        routine_id = int(data.split(":")[1])
        rendered = _render_routine_view_message(routine_id, user_id)
        if rendered is None:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        text, markup = rendered
        await query.edit_message_text(text, reply_markup=markup)
```

- [ ] **Step 3: Manual smoke test — legend update visible**

Restart the bot (`python bot.py` or whatever the local invocation is). In Telegram:
1. Open the main menu, tap `Routines`, tap any existing routine (or create one with at least one item).
2. Verify the body line now reads: `[+] taken — tap to undo  [-] tap to take  [·] not due — tap to manage`.
3. Tap an item — note that it still opens the **detail** screen (period, start date, Delete, Back). That's expected at this stage; tap routing changes in Task 3.

If you have no routines yet: from the main menu, tap `Routines` → `Add routine`, name it `Test`, pick a time, then add a cream named `Test cream`, period `Every day`. Then tap into the routine to see the legend.

- [ ] **Step 4: Commit**

```bash
git add handlers.py
git commit -m "refactor: extract routine view renderer; update legend wording"
```

---

## Task 3: Wire item-row tap routing by state, drop the "Logged" confirmation, add untake callback

**Files:**
- Modify: `handlers.py`

This is the substantive change. It touches three things together so the UX stays consistent:
1. `get_routine_view_keyboard` routes each item-row button based on the item's state.
2. The existing `routine_item_taken:` branch stops emitting `Logged {name} as taken!` — it now silently re-renders the routine view via the helper from Task 2.
3. A new `routine_item_untake:<id>` branch deletes today's log and re-arms the follow-up if needed.

- [ ] **Step 1: Update `get_routine_view_keyboard` to route by state**

Find `get_routine_view_keyboard` in `handlers.py` (currently lines 236-271). Replace the inner loop that builds item buttons (lines 247-260) with:

```python
    buttons = []
    for item in routine["items"]:
        if not item["due_today"]:
            status = "·"
            callback = f"routine_item_view:{item['id']}"
        elif item["id"] in taken_ids:
            status = "+"
            callback = f"routine_item_untake:{item['id']}"
        else:
            status = "-"
            callback = f"routine_item_taken:{item['id']}"
        emoji = "🧴" if item["type"] == "cream" else "💊"
        period_label = {1: "daily", 2: "every 2 days", 3: "every 3 days", 7: "weekly"}.get(
            item["period_days"], f"every {item['period_days']} days"
        )
        label = f"[{status}] {emoji} {item['name']} — {period_label}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])
```

The rest of the function (the trailing `Add cream / Add pill / Edit time / Delete routine / Back` rows) is unchanged.

- [ ] **Step 2: Replace the `routine_item_taken:` branch body**

Find the existing `routine_item_taken:` branch in `button_callback` (currently lines 939-968). Replace it with:

```python
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

        rendered = _render_routine_view_message(item["routine_id"], user_id)
        if rendered is None:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        text, markup = rendered
        await query.edit_message_text(text, reply_markup=markup)
```

The only behavioral changes versus the existing branch are the final three lines (it now renders the routine view body via the helper instead of writing `f"Logged {item['name']} as taken!"` and attaching the keyboard).

- [ ] **Step 3: Add the new `routine_item_untake:` branch**

Insert a new `elif` branch immediately **after** the `routine_item_taken:` branch you just edited:

```python
    elif data.startswith("routine_item_untake:"):
        from datetime import datetime, time as dt_time
        from zoneinfo import ZoneInfo

        item_id = int(data.split(":")[1])
        item = db.get_routine_item(item_id)
        if not item:
            await query.edit_message_text(
                "Item not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return

        try:
            user_tz = ZoneInfo(user.get("timezone", "UTC"))
        except Exception:
            user_tz = ZoneInfo("UTC")
        now_local = datetime.now(user_tz)
        today_local = now_local.date()

        db.delete_today_routine_item_log(item_id, user_id, today=today_local)

        routine = db.get_routine(item["routine_id"], today=today_local)
        if routine is not None:
            today_logs_after = db.get_today_routine_item_logs(user_id, today=today_local)
            taken_ids = {log["routine_item_id"] for log in today_logs_after}
            still_due = [
                i for i in routine["items"]
                if i["due_today"] and i["id"] not in taken_ids
            ]
            fire_time = dt_time(routine["remind_at_hour"], routine["remind_at_minute"])
            if still_due and now_local.time() >= fire_time:
                from scheduler import schedule_routine_followup
                schedule_routine_followup(context, item["routine_id"], user_id)

        rendered = _render_routine_view_message(item["routine_id"], user_id)
        if rendered is None:
            await query.edit_message_text(
                "Routine not found.",
                reply_markup=get_routines_keyboard(user_id)
            )
            return
        text, markup = rendered
        await query.edit_message_text(text, reply_markup=markup)
```

Notes:
- `user` and `context` are already in scope (set at the top of `button_callback`).
- The `from scheduler import schedule_routine_followup` lives inside the branch to mirror the existing in-branch import style elsewhere in this file (e.g., the existing `routine_item_taken:` does `from scheduler import cancel_routine_followup` inline at line 954).
- We pass `today=today_local` to both `db.get_routine` and `db.get_today_routine_item_logs` so the "due_today" computation respects the user's timezone, mirroring `scheduler._due_not_taken_items` (scheduler.py:282-293).

- [ ] **Step 4: Manual smoke test — take and untake**

Restart the bot. In Telegram:
1. From the main menu, tap `Routines`, tap a routine that has at least one daily item.
2. Confirm the item shows as `[-] 🧴 <name> — daily`. Tap it.
3. Verify the message stays as the routine view (header `{name} — HH:MM`, the new legend, and the same set of buttons), but the row now shows `[+]`. No "Logged X as taken!" line should appear.
4. Tap the same row again. Verify the row toggles back to `[-]` and the message body remains the routine view.
5. Tap a non-due item (a `[·]` row, e.g., from a routine with `every 2 days` not aligned to today). Verify it still opens the **detail** screen.

- [ ] **Step 5: Manual smoke test — follow-up re-arm**

Use a routine with a fire time **earlier than now** today (so the daily reminder has already fired). Easiest: create a fresh routine with a fire-time of 1-2 hours before "now" in your timezone, add a daily cream, wait for the reminder to fire (or trigger it manually by setting the time slightly in the future and waiting). Or: re-use a routine whose reminder fired earlier today.

1. From the routine view, tap a `[+]` (taken) item to untake it.
2. Wait ~30 minutes (or temporarily lower the follow-up interval in `scheduler.schedule_routine_followup` for the test, then revert).
3. Verify the follow-up reminder message arrives with the just-untaken item listed.

For the inverse case: create a routine with a fire-time **later today**, untake an item from its view (you'd have had to mark it taken pre-emptively first). Verify no follow-up is sent — the daily job will fire normally at its scheduled time. (This case is harder to exercise; it's enough to confirm by reading the branch logic that `schedule_routine_followup` is gated by `now_local.time() >= fire_time`.)

- [ ] **Step 6: Commit**

```bash
git add handlers.py
git commit -m "feat: tap-to-toggle take/untake from routine view"
```

---

## Task 4: Final regression sweep

**Files:** none.

This task ensures we didn't break adjacent flows that share code paths.

- [ ] **Step 1: Reminder-tap path still works**

Trigger or wait for a routine reminder to fire (the `🧴💊 {name} — time to apply/take!` message with `Taken: {item}` buttons). Tap one of the buttons. Verify:
- The reminder message is replaced by the routine-view body (header + legend), not by `Logged {name} as taken!`.
- The just-tapped item's row shows `[+]`.
- If other due items remain, the follow-up still re-fires every 30 min (existing behavior, unchanged).

- [ ] **Step 2: Item detail still reachable**

In a routine view, tap a `[·]` (not-due) item. Confirm the detail screen opens with `Delete` and `Back` buttons, exactly as before. Tap `Delete`, confirm the item is removed and the routine view is shown.

- [ ] **Step 3: Routine creation / item add unchanged**

From `Routines` → `Add routine`, walk through the full create flow (name, time, add cream, pick period). Confirm the routine view that's displayed at the end shows the new legend and routes taps correctly.

- [ ] **Step 4: History still works**

From the routine view (or routines list), tap `History`. Confirm the 7-day history message renders unchanged.

- [ ] **Step 5: No commit unless something is broken**

If everything passes, no commit is needed for this task. If you needed a fix, commit it with a descriptive message scoped to the regression.
