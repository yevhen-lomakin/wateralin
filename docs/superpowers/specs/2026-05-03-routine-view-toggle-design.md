# Routine View — Direct-Tap Toggle Design

Allow users to mark routine items as taken (and untake them) directly from the **routine view** menu — the screen reached via `Routines → tap a routine`. Today, marking-taken is only possible from the daily reminder message; if that message scrolled away or the user took the cream/pill before the reminder fired, there is no way to record it without going back to the reminder.

This is a small UX change to one keyboard's tap routing, plus one new database function.

## Problem

Two menus currently surface routine items:

1. **Reminder menu** (`scheduler._build_routine_reminder`) — sent at the routine's fire time. Renders one `Taken: <name>` button per due-and-not-taken item. Tapping logs the item.
2. **Routine view menu** (`handlers.get_routine_view_keyboard`) — reached from the main menu. Renders each item with a status marker (`[+]`, `[-]`, `[·]`), but tapping a row opens the item *detail* screen (period, start date, delete). There is no "mark taken" affordance.

Users want the routine view to also support marking taken.

## Behavior

In the routine view, each item row's tap action depends on its state:

| Marker | State | Tap action |
|---|---|---|
| `[-]` | due today, not taken | log as taken; re-render routine view with `[+]` |
| `[+]` | taken today | remove today's log; re-render with `[-]` |
| `[·]` | not due today | open item detail (current behavior, unchanged) |

After any tap, the routine view message is edited in place (`query.edit_message_text`) so only the marker changes — no confirmation line.

This is a behavior change in the existing `routine_item_taken` handler: today it sets the message body to `Logged {name} as taken!` before attaching `get_routine_view_keyboard` (`handlers.py:965-968`). After this change, both `routine_item_taken` and the new `routine_item_untake` re-render the standard routine view body: `{name} — HH:MM\n\n{legend}`. This applies in both contexts where `routine_item_taken` can be triggered (reminder message tap and routine view tap).

The body line below the header is adjusted to reflect the new affordance:

- Old: `[+] taken today  [-] due but not taken  [·] not due today`
- New: `[+] taken — tap to undo  [-] tap to take  [·] not due — tap to manage`

The header (`{name} — HH:MM`) is unchanged.

The "no items yet" body (`No items yet. Add creams or pills:`) is unchanged.

## Callback routes

One new callback added to `handlers.button_callback`:

- `routine_item_untake:<item_id>` — delete today's log for the item, then refresh the routine view. Re-arms the follow-up reminder if the conditions in the next section are met.

The existing `routine_item_taken:<id>` route is reused for both reminder taps and routine-view taps. Its only behavior change is the post-tap message body, described in the **Behavior** section above.

## Follow-up reminder interaction

`routine_item_taken` already cancels the routine's follow-up job once all due items for the day are marked taken (`handlers.py:954-963`). The new `routine_item_untake` is the inverse:

After deleting the log, if **both** of these are true, schedule the follow-up:

1. There is now at least one due-and-not-taken item in the routine (in user tz).
2. The routine's daily fire time has already passed today (in user tz). Equivalent to: `datetime.now(user_tz).time() >= time(remind_at_hour, remind_at_minute)`.

If the daily fire time has not yet passed, do nothing — the daily job will fire as scheduled and start the follow-up itself.

If condition 1 is false (no due-not-taken items remain), do nothing.

Use the existing `scheduler.schedule_routine_followup(context, routine_id, user_id)` — it already removes any existing follow-up before creating a new one, so calling it on top of an already-running follow-up is safe.

## Database

One new function in `database.py`:

```python
def delete_today_routine_item_log(item_id: int, user_id: int, today: date | None = None) -> int:
    """Delete any routine_item_logs rows for this item+user dated today.
    Returns the number of rows deleted. Idempotent: returns 0 if none exist."""
```

- `today` defaults to `date.today()`. Callers pass an explicit `today` derived from the user's timezone, matching the pattern already used by `_due_not_taken_items` in scheduler.py.
- Implementation: `DELETE FROM routine_item_logs WHERE routine_item_id = ? AND user_id = ? AND DATE(applied_at) = ?`.

The existing `routine_item_logs` schema is unchanged.

## Detail screen (unchanged)

`routine_item_view:<item_id>` keeps its current contents: emoji + name, period label, start date, `Delete`, `Back`. It is still reachable by tapping `[·]` rows.

## Non-goals

- A path to delete an item while it is `[-]` or `[+]` today. Workaround: wait until the next day when the item shows as `[·]`, or delete the entire routine. The detail screen is intentionally not reachable from due-today rows — direct tap is committed to toggling.
- Untaking an item from the original reminder message. Reminder message buttons remain take-only; untake is only available from the routine view.
- Multi-day untake (e.g., "I didn't actually take it yesterday"). Untake operates only on today's log.
- Editing the legend wording or item-row label format beyond the marker change.

## Files changed

- `handlers.py` — change tap target for due/taken items in `get_routine_view_keyboard` (currently always `routine_item_view:<id>`; new code routes to `routine_item_taken:<id>`, `routine_item_untake:<id>`, or `routine_item_view:<id>` based on the item's state). Update the legend line in the `routine_view:` callback. Adjust `routine_item_taken` to render the standard routine view body instead of `Logged X as taken!`. Add a `routine_item_untake:<id>` branch in `button_callback`.
- `database.py` — add `delete_today_routine_item_log`.
- `scheduler.py` — no changes; the existing `cancel_routine_followup` and `schedule_routine_followup` are reused.

## End-to-end example

1. User has routine "Morning face" at 08:00 with two daily items: Retinol, Vit C.
2. At 08:00 the reminder fires with two `Taken: …` buttons. User taps `Taken: Vit C`. Follow-up reschedules every 30 min for Retinol only.
3. User opens main menu → `Routines` → `Morning face`. View shows `[+] 🧴 Vit C — daily` and `[-] 🧴 Retinol — daily`.
4. User taps the Retinol row. Log written. View re-renders to `[+] 🧴 Vit C — daily` and `[+] 🧴 Retinol — daily`. Follow-up cancels itself on next tick (no due-not-taken items remain).
5. User realizes they confused Retinol with another cream and didn't actually take it. Taps `[+] 🧴 Retinol — daily`. Today's Retinol log is deleted. View re-renders to `[-]`. The fire time (08:00) has already passed, so `schedule_routine_followup` is called — the user will be re-reminded in 30 min.
