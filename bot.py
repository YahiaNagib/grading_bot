import os
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.cloud import vision
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler, PicklePersistence, CallbackQueryHandler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

allowed_users_str = os.getenv('ALLOWED_USERS')

# 2. Convert it into a list of integers
if allowed_users_str:
    # This splits the string by commas, removes any accidental spaces, and turns them into numbers
    ALLOWED_USERS = [int(user_id.strip()) for user_id in allowed_users_str.split(',')]
else:
    # Failsafe: if the variable is missing, lock the bot down so nobody can use it
    ALLOWED_USERS = [] 
    print("⚠️ WARNING: ALLOWED_USERS is empty. The bot is locked.")

google_creds_string = os.getenv('GOOGLE_CREDENTIALS')
if not google_creds_string:
    raise ValueError("Missing GOOGLE_CREDENTIALS environment variable!")

creds_dict = json.loads(google_creds_string)

# --- GOOGLE SHEETS SETUP ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instructions for the user."""
    msg = (
        "Welcome to the Grading Bot!\n\n"
        "Please configure your settings using the following commands:\n"
        "1. `/addsheet <name> <URL>` - Save a new spreadsheet\n"
        "2. `/listsheets` - See all your saved sheets (Interactive)\n"
        "3. `/setworksheet` - Choose a specific tab (Worksheet)\n"
        # "4. `/selectsheet <name>` - Switch to a different spreadsheet\n"
        "4. `/delsheet <name>` - Remove a sheet from your list\n\n"
        "Other settings:\n"
        "- `/setidcol <number>` - Set ID column (e.g., 2 for B)\n"
        "- `/setmarkcol <number>` - Set Marks column (e.g., 4 for D)\n"
        "- `/settings` - View current setup"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extracts the Sheet ID from the URL and saves it as 'Main'."""
    
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        # Get the URL the user typed after the command
        url = context.args[0] 
        # Extract the ID from the middle of the Google Sheets URL
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        
        if match:
            sheet_id = match.group(1)
            if 'saved_sheets' not in context.user_data:
                context.user_data['saved_sheets'] = {}
            
            context.user_data['saved_sheets']['Main'] = sheet_id
            context.user_data['sheet_id'] = sheet_id
            context.user_data['active_sheet_name'] = 'Main'
            
            await update.message.reply_text("✅ Spreadsheet linked as 'Main' and set as active!")
        else:
            await update.message.reply_text("❌ Invalid URL. Please provide a full Google Sheets URL.")
    except IndexError:
        await update.message.reply_text("❌ Please provide a URL. Example: `/seturl https://docs.google...`")

async def add_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a new spreadsheet to the saved list."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        name = context.args[0]
        url = context.args[1]
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        
        if match:
            sheet_id = match.group(1)
            if 'saved_sheets' not in context.user_data:
                context.user_data['saved_sheets'] = {}
            
            context.user_data['saved_sheets'][name] = sheet_id
            
            # If no active sheet, set this one
            if 'active_sheet_name' not in context.user_data:
                context.user_data['active_sheet_name'] = name
                context.user_data['sheet_id'] = sheet_id
                await update.message.reply_text(f"✅ Sheet '{name}' added and set as active!")
            else:
                await update.message.reply_text(f"✅ Sheet '{name}' added to your list!")
        else:
            await update.message.reply_text("❌ Invalid URL. Please provide a full Google Sheets URL.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usage: `/addsheet <name> <url>`")

async def list_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all saved spreadsheets with interactive buttons."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    sheets = context.user_data.get('saved_sheets', {})
    active = context.user_data.get('active_sheet_name')
    
    if not sheets:
        await update.message.reply_text("No sheets saved yet. Use `/addsheet <name> <url>` to add one.")
        return
    
    keyboard = []
    for name in sheets:
        label = f"{name} ✅" if name == active else name
        keyboard.append([InlineKeyboardButton(label, callback_data=f"select_ss:{name}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📂 **Select a spreadsheet to make it active:**", reply_markup=reply_markup, parse_mode='Markdown')

async def list_worksheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all worksheets (tabs) in the active spreadsheet."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    sheet_id = context.user_data.get('sheet_id')
    if not sheet_id:
        await update.message.reply_text("❌ No active spreadsheet. Use `/listsheets` to select one first.")
        return
    
    await update.message.reply_text("🔄 Fetching worksheets...")
    
    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheets = spreadsheet.worksheets()
        active_ws = context.user_data.get('active_worksheet')
        
        keyboard = []
        for ws in worksheets:
            label = f"{ws.title} ✅" if ws.title == active_ws else ws.title
            keyboard.append([InlineKeyboardButton(label, callback_data=f"select_ws:{ws.title}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📑 **Select a worksheet (tab) to use:**", reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching worksheets: {str(e)}")

async def list_columns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides an interface to set ID and Mark columns."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    id_col = context.user_data.get('id_col', 'Not Set')
    mark_col = context.user_data.get('mark_col', 'Not Set')
    
    keyboard = [
        [InlineKeyboardButton(f"Set ID Column (Current: {id_col})", callback_data="prompt_id_col")],
        [InlineKeyboardButton(f"Set Mark Column (Current: {mark_col})", callback_data="prompt_mark_col")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ **Column Configuration**\n\n"
        "Click a button below to update the column indices:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks for sheet, worksheet, and column selection."""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ALLOWED_USERS:
        return
    
    data = query.data
    
    if data.startswith("select_ss:"):
        name = data.split(":", 1)[1]
        sheets = context.user_data.get('saved_sheets', {})
        if name in sheets:
            context.user_data['active_sheet_name'] = name
            context.user_data['sheet_id'] = sheets[name]
            context.user_data['active_worksheet'] = None
            await query.edit_message_text(f"🎯 Switched to spreadsheet: **{name}**\n\nNow use `/setworksheet` to pick a tab.", parse_mode='Markdown')
            
    elif data.startswith("select_ws:"):
        ws_name = data.split(":", 1)[1]
        context.user_data['active_worksheet'] = ws_name
        await query.edit_message_text(f"📑 Active worksheet set to: **{ws_name}**", parse_mode='Markdown')

    elif data == "prompt_id_col":
        context.user_data['state'] = 'AWAITING_ID_COL'
        await query.edit_message_text("🔢 Please send the **ID column number** (e.g., 2 for column B):", parse_mode='Markdown')

    elif data == "prompt_mark_col":
        context.user_data['state'] = 'AWAITING_MARK_COL'
        await query.edit_message_text("🔢 Please send the **Mark column number** (e.g., 4 for column D):", parse_mode='Markdown')

async def select_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Selects an active spreadsheet from the saved list."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        name = context.args[0]
        sheets = context.user_data.get('saved_sheets', {})
        
        if name in sheets:
            context.user_data['active_sheet_name'] = name
            context.user_data['sheet_id'] = sheets[name]
            await update.message.reply_text(f"🎯 Switched to spreadsheet: **{name}**", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Sheet '{name}' not found. Use `/listsheets` to see saved sheets.")
    except IndexError:
        await update.message.reply_text("❌ Usage: `/selectsheet <name>`")

async def del_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes a spreadsheet from the saved list."""
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        name = context.args[0]
        sheets = context.user_data.get('saved_sheets', {})
        
        if name in sheets:
            del context.user_data['saved_sheets'][name]
            if context.user_data.get('active_sheet_name') == name:
                del context.user_data['active_sheet_name']
                if not context.user_data['saved_sheets']:
                    if 'sheet_id' in context.user_data:
                        del context.user_data['sheet_id']
                else:
                    # Pick another one as active automatically
                    new_active = next(iter(context.user_data['saved_sheets']))
                    context.user_data['active_sheet_name'] = new_active
                    context.user_data['sheet_id'] = context.user_data['saved_sheets'][new_active]
                    await update.message.reply_text(f"🗑️ Sheet '{name}' removed. Active sheet is now '{new_active}'.")
                    return
            await update.message.reply_text(f"🗑️ Sheet '{name}' removed.")
        else:
            await update.message.reply_text(f"❌ Sheet '{name}' not found.")
    except IndexError:
        await update.message.reply_text("❌ Usage: `/delsheet <name>`")

async def set_id_col(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        col_num = int(context.args[0])
        context.user_data['id_col'] = col_num
        await update.message.reply_text(f"✅ IDs will now be read from column {col_num}.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Please provide a valid number. Example: `/setidcol 2`")

async def set_mark_col(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    try:
        col_num = int(context.args[0])
        context.user_data['mark_col'] = col_num
        await update.message.reply_text(f"✅ Marks will now be saved to column {col_num}.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Please provide a valid number. Example: `/setmarkcol 4`")

async def view_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return
    
    """Shows the user their current configuration."""
    active_sheet = context.user_data.get('active_sheet_name', 'Not Set')
    active_ws = context.user_data.get('active_worksheet', 'sheet1 (Default)')
    sheet_id = context.user_data.get('sheet_id', 'Not Set')
    id_col = context.user_data.get('id_col', 'Not Set')
    mark_col = context.user_data.get('mark_col', 'Not Set')
    saved_sheets = context.user_data.get('saved_sheets', {})
    
    sheets_list = "\n".join([f"- {name}" for name in saved_sheets]) if saved_sheets else "None"
    
    await update.message.reply_text(
        f"📊 **Current Settings**\n"
        f"Active Spreadsheet: **{active_sheet}**\n"
        f"Active Worksheet: **{active_ws}**\n"
        f"Sheet ID: `{sheet_id[:10]}...`\n"
        f"ID Column: {id_col}\n"
        f"Marks Column: {mark_col}\n\n"
        f"📂 **Saved Sheets:**\n{sheets_list}",
        parse_mode='Markdown'
    )

def extract_ids_and_marks(text):
    """Helper function to find and categorize numbers."""
    all_numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
    
    ids = []
    marks = []
    
    # 2. Categorize them safely
    for num in all_numbers:
        # If it has a decimal point, it is definitely a mark
        if '.' in num:
            marks.append(num)
        # If no decimal and 4 or more digits, it's an ID
        elif len(num) >= 4:
            ids.append(num)
        # Otherwise, it's a standard whole-number mark (3 digits or fewer)
        else:
            marks.append(num)
            
    return ids, marks

def detect_text(image_path):
    """Run Google Cloud Vision OCR on the image."""
    vision_client = vision.ImageAnnotatorClient.from_service_account_info(creds_dict)
    with open(image_path, "rb") as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)
    # Using document_text_detection handles handwriting better than standard text_detection
    response = vision_client.document_text_detection(image=image)
    
    if response.error.message:
        raise Exception(f"Vision API Error: {response.error.message}")
        
    return response.text_annotations[0].description if response.text_annotations else ""

def parse_and_update(text, sheet_id, id_column, mark_column, worksheet_name=None):
    """Extract IDs/Marks regardless of layout and update the sheet."""

    try:
        spreadsheet = client.open_by_key(sheet_id)
        if worksheet_name:
            sheet = spreadsheet.worksheet(worksheet_name)
        else:
            sheet = spreadsheet.sheet1
    except Exception as e:
        return f"Error connecting to sheet: {str(e)}. Make sure you shared it with the bot's email!"

    ids, marks = extract_ids_and_marks(text)

    results = []
    # Fetch all current IDs from the sheet to find the right row to update
    existing_ids = sheet.col_values(id_column)

    # Pair the categorized lists back together sequentially
    for i in range(len(ids)):
        student_id = ids[i]
        
        mark = 1 if not marks else marks[i]
        
        try:
            # +1 because spreadsheet index starts at 1
            row_index = existing_ids.index(student_id) + 1 
            # Update Column B (Marks) for that specific row
            sheet.update_cell(row_index, mark_column, mark) 
            results.append(f"Updated ID {student_id} with mark {mark}")
        except ValueError:
            results.append(f"ID {student_id} not found in spreadsheet.")
            
    return "\n".join(results)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return 

    """Triggered when the bot receives a photo."""
    await update.message.reply_text("Image received. Processing handwriting...")
    
    try:
        # Download the highest resolution photo sent
        photo_file = await update.message.photo[-1].get_file()
        image_path = "temp_image.jpg"
        await photo_file.download_to_drive(image_path)
        
        # 1. Read Text
        extracted_text = detect_text(image_path)

        # await update.message.reply_text(extracted_text)
        # 2. Parse and Update Sheets
        # feedback = parse_and_update(extracted_text)
        # Find every isolated group of numbers in the entire text block
         
        ids, marks = extract_ids_and_marks(extracted_text)

        # --- Safety Checks ---
        # if not ids or not marks:
        #     await update.message.reply_text("Could not find any valid numbers in the image.")
        #     return "Could not find any valid numbers in the image."
            
        # # If the bot found an unequal amount of IDs and Marks, it shouldn't guess
        # if len(ids) != len(marks):
        #     await update.message.reply_text(f"Mismatch Error: I found {len(ids)} IDs but {len(marks)} marks. Please retake the photo.")
        #     return f"Mismatch Error: I found {len(ids)} IDs but {len(marks)} marks. Please retake the photo."
        

        # await update.message.reply_text(f"Processing Complete:\n{feedback}")

        if marks:
            data = "\n".join([f"{i} {m}" for i, m in zip(ids, marks)])
        else:
            data = ids
            
        # await update.message.reply_text(extracted_text)
        await update.message.reply_text(data)
        await update.message.reply_text("Please copy and paste the data then edit if required, then send it back to me.")
        
        # 3. Clean up and Reply
        os.remove(image_path)
        
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.from_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Unauthorized access.")
        return 

    """Triggered when the bot receives standard text."""
    
    state = context.user_data.get('state')
    user_text = update.message.text

    if state == 'AWAITING_ID_COL':
        try:
            col_num = int(user_text)
            context.user_data['id_col'] = col_num
            context.user_data['state'] = None
            await update.message.reply_text(f"✅ ID column set to **{col_num}**.", parse_mode='Markdown')
            return
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please send a **number** for the ID column:")
            return

    if state == 'AWAITING_MARK_COL':
        try:
            col_num = int(user_text)
            context.user_data['mark_col'] = col_num
            context.user_data['state'] = None
            await update.message.reply_text(f"✅ Mark column set to **{col_num}**.", parse_mode='Markdown')
            return
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please send a **number** for the Mark column:")
            return

    """Processes data and saves immediately."""
    sheet_id = context.user_data.get('sheet_id')
    id_col = context.user_data.get('id_col')
    mark_col = context.user_data.get('mark_col')
    active_ws = context.user_data.get('active_worksheet')
    
    if not all([sheet_id, id_col, mark_col]):
        await update.message.reply_text("⚠️ Please complete your setup first using /seturl or /listsheets, and /setcols.")
        return
    # --------------------

    # Send a quick loading message so the user knows it registered
    await update.message.reply_text("Processing...")
    
    try:
        # Pass the multiline text directly to your existing parser
        feedback = parse_and_update(user_text, sheet_id, id_col, mark_col, worksheet_name=active_ws)
        
        # Send the final results back to the user

        if "error" in feedback.lower():
            await update.message.reply_text(f"❌ An error occurred: {feedback}")
        else:
            await update.message.reply_text(f"✅ Done!\n{feedback}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

async def setup_menu(application: Application):
    """Pushes the command menu to Telegram on startup."""
    commands = [
        BotCommand("start", "Show instructions"),
        BotCommand("settings", "View current configuration"),
        BotCommand("addsheet", "Save a new sheet: /addsheet <name> <url>"),
        BotCommand("listsheets", "Select a spreadsheet"),
        BotCommand("setworksheet", "Select a worksheet tab"),
        BotCommand("setcols", "Set ID and Mark columns"),
        BotCommand("selectsheet", "Switch active sheet: /selectsheet <name>"),
        BotCommand("delsheet", "Remove a sheet: /delsheet <name>"),
        # BotCommand("setidcol", "Set ID column (Command)"),
        # BotCommand("setmarkcol", "Set Marks column (Command)"),
        # BotCommand("seturl", "Quick link a sheet as 'Main'")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Start the bot."""

    if os.getenv('RAILWAY_ENVIRONMENT'):
        data_path = "/data/bot_data.pickle"
    else:
        data_path = "bot_data.pickle"

    persistence = PicklePersistence(filepath=data_path)
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(setup_menu).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("settings", view_settings))
    # application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("addsheet", add_sheet))
    application.add_handler(CommandHandler("listsheets", list_sheets))
    application.add_handler(CommandHandler("setworksheet", list_worksheets))
    application.add_handler(CommandHandler("setcols", list_columns))
    application.add_handler(CommandHandler("selectsheet", select_sheet))
    application.add_handler(CommandHandler("delsheet", del_sheet))
    # application.add_handler(CommandHandler("setidcol", set_id_col))
    # application.add_handler(CommandHandler("setmarkcol", set_mark_col))
    
    # Callback query handler for interactive buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Listen specifically for photo uploads
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Grading bot is running locally. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()