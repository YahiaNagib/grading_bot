# Grading Bot: Code Summary

## What the bot does

`bot.py` is a Telegram bot for entering grades. You send it a photo of a handwritten list of student IDs and marks. Google's Gemini API reads the image and returns the ID/mark pairs, and the bot sends them back as text (`1590 3, 3132 5, …`). If a row has only an ID, its mark defaults to `1`. You check or fix that text and send it back, and the bot writes each mark into a Google Sheet, on the row where that student's ID appears.

Only Telegram user IDs listed in `ALLOWED_USERS` can use it. Each user's settings (saved sheets, active tab, column numbers) are kept in `bot_data.pickle`, so they survive restarts.

## Workflow

```
1. Setup (once per spreadsheet)
   /addsheet <name> <url>  → save a spreadsheet
   /listsheets             → tap a button to make it active
   /setworksheet           → tap a button to pick a tab
   /setcols                → tap a button, then type the ID and Mark column numbers

2. Grading
   Send a photo → Gemini → bot replies with "1590 3, 3132 5, …"
   Copy, fix if needed, send the text back
   → bot finds each ID in the ID column and writes the mark in the Mark column on that row
   → bot replies with "Updated ID …" or "ID … not found" for each line
```

The photo step never writes to the sheet. Only text you send back does, which gives you a chance to correct reading mistakes first.

## Configuration

| Environment variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `ALLOWED_USERS` | Comma-separated Telegram user IDs allowed to use the bot. If empty, nobody can use it |
| `GOOGLE_CREDENTIALS` | Google service-account JSON, as a string. Used for Google Sheets |
| `GEMINI_API_KEY` | Gemini API key from Google AI Studio. Used to read the photos |
| `GEMINI_MODEL` | Optional. Gemini model to use (default `gemini-2.5-flash`) |
| `RAILWAY_ENVIRONMENT` | If set, settings are stored in `/data/bot_data.pickle` instead of `bot_data.pickle` |

Each spreadsheet must be shared with the service account's email address, or the bot can't open it.

## Startup

- **Module level:** loads `.env`, reads the environment variables above, logs in to Google Sheets with `gspread`, and creates the Gemini client.
- **`main()`:** sets up storage in the pickle file, connects each command, button and message type to its function, and starts listening for messages.
- **`setup_menu()`:** runs after startup and sets the command list Telegram shows when you type `/`.

## Command functions

| Function | Command | Purpose |
|---|---|---|
| `start_command` | `/start` | Shows the instructions |
| `add_sheet` | `/addsheet <name> <url>` | Pulls the sheet ID out of the URL and saves it under a name. Makes it active if no sheet is active yet |
| `list_sheets` | `/listsheets` | One button per saved sheet; the active one has ✅ |
| `select_sheet` | `/selectsheet <name>` | Same as tapping a sheet button, but by typing its name. Loads that sheet's ID and column settings |
| `del_sheet` | `/delsheet <name>` | Removes a saved sheet. If it was the active one, the next saved sheet becomes active |
| `list_worksheets` | `/setworksheet` | Opens the active spreadsheet and shows a button for each tab |
| `list_columns` | `/setcols` | Two buttons to set the ID column and the Mark column, showing the current values |
| `view_settings` | `/settings` | Shows the active sheet, tab, sheet ID, columns, and all saved sheets |
| `set_url` | `/seturl` (turned off) | Older single-sheet setup that saves the sheet as "Main" |
| `set_id_col` / `set_mark_col` | `/setidcol`, `/setmarkcol` (turned off) | Older typed commands for setting the columns |

## Button handler

**`button_callback`** handles every button press:

- `select_ss:<name>`: makes that spreadsheet active, loads its saved columns, and clears the chosen tab.
- `select_ws:<tab>`: sets the active tab.
- `prompt_id_col` / `prompt_mark_col`: puts the user in a "waiting for a column number" state (`AWAITING_ID_COL` or `AWAITING_MARK_COL`) so the next text message is read as that number.

## Message handlers

- **`handle_photo`:** downloads the photo into memory and calls `extract_pairs_from_image`. It replies with the pairs as `1590 3, 3132 5, …` and asks you to edit them and send them back. If no IDs are found, it asks you to retake the photo. It doesn't write to the sheet.
- **`handle_text`** has two jobs:
  1. If the user is in a waiting state, it saves the number as the ID or Mark column (for the active sheet too) and clears the state.
  2. Otherwise, if setup is complete, it treats the text as grade data and calls `parse_and_update`.

## Helper functions

- **`extract_pairs_from_image(image_bytes)`:** sends the image to Gemini with a prompt and a JSON schema (`StudentMark`: `id` plus an optional `mark`), so Gemini returns structured rows instead of raw text. It drops rows whose ID isn't a plain number (such as a header), sets missing marks to `"1"`, and returns a list of `(id, mark)` pairs.
- **`extract_ids_and_marks(text)`:** used on the text you send back. It finds every number and sorts it:
  - has a decimal point → mark
  - 4 or more digits → student ID
  - 3 digits or fewer → mark
- **`parse_and_update(text, sheet_id, id_column, mark_column, worksheet_name)`:** opens the chosen tab (or the first tab), reads the whole ID column, and pairs the i-th ID with the i-th mark. It finds each ID's row and writes the mark there. If the text has no marks at all, every ID gets a mark of `1`, which works for taking attendance.

## Per-sheet settings

Each entry in `saved_sheets` stores its own column settings:

```python
{'sheet_id': ..., 'id_col': ..., 'mark_col': ...}
```

Switching sheets loads that sheet's columns, and setting a column saves it to the active sheet. Entries saved in the older format (just the sheet ID as a string) are converted to this format the first time they're used.

## Known issues

- **`/start` lists commands that don't work:** it tells users about `/setidcol` and `/setmarkcol`, but their handlers are turned off. The setup warning in `handle_text` also mentions `/seturl`, which is turned off.
- **More IDs than marks fails:** `marks[i]` in `parse_and_update` raises `IndexError`. It's only caught by the general handler in `handle_text`, so IDs already updated stay written and the rest are skipped without a per-ID message. Replies from the photo step always include a mark for every ID, so this only happens if you delete marks when editing.
- **IDs must match exactly:** `existing_ids.index(student_id)` is an exact text comparison, so a cell like `"1234 "` or `1234.0` won't be found.
- **Docstrings after the access check:** in `view_settings`, `handle_photo` and `handle_text`, the docstring comes after the access check, so Python treats it as a plain string rather than the function's docstring. This has no effect on behaviour.
