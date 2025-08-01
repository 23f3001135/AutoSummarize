import logging
import os
import json
from pathlib import Path
from functools import wraps
from typing import Callable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
# --- NEW: Import HTTPXRequest to customize timeouts ---
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# --- 1. Initial Setup & Configuration ---

# Load environment variables from a .env file for security
load_dotenv()

# Configuration constants
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
VERIFICATION_CODE = os.getenv("VERIFICATION_CODE")
MEDIA_SAVE_DIR = Path("telegram_media")
VERIFIED_USERS_FILE = Path("verified_users.json")

# In-memory set for fast lookups of verified user IDs
VERIFIED_USERS = set()

# Enable logging to see errors and bot activity
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- 2. User Verification & Persistence ---

def load_verified_users():
    """Loads verified user IDs from the JSON file into the in-memory set."""
    global VERIFIED_USERS
    if VERIFIED_USERS_FILE.exists():
        try:
            with open(VERIFIED_USERS_FILE, "r") as f:
                user_ids = json.load(f)
                VERIFIED_USERS = set(user_ids)
            logger.info(f"Loaded {len(VERIFIED_USERS)} verified users.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Could not load verified users from {VERIFIED_USERS_FILE}: {e}")
            VERIFIED_USERS = set()

def save_verified_users():
    """Saves the current set of verified user IDs to the JSON file."""
    try:
        with open(VERIFIED_USERS_FILE, "w") as f:
            json.dump(list(VERIFIED_USERS), f, indent=4)
    except IOError as e:
        logger.error(f"Could not save verified users to {VERIFIED_USERS_FILE}: {e}")

def verified_only(func: Callable) -> Callable:
    """Decorator to restrict a handler to only verified users."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> None:
        if update.effective_user and update.effective_user.id in VERIFIED_USERS:
            await func(update, context, *args, **kwargs)
        else:
            user_id = "unknown"
            if update.effective_user:
                user_id = update.effective_user.id
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            if update.message:
                await update.message.reply_text(
                    "❌ Access Denied. This is a private bot.\n\n"
                    f"Please verify yourself using the `/verify <your_code>` command."
                )
    return wrapper


# --- 3. Core Bot Logic & Media Processing ---

async def process_media_file(file_path: Path, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """This is the modular function for processing a saved file."""
    logger.info(f"Processing file: {file_path}")
    await update.message.reply_text(
        f"✅ File saved and processed successfully!\n"
        f"Server path: `{file_path}`"
    )


# --- 4. Telegram Command and Message Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and guides users toward verification."""
    user = update.effective_user
    if user.id in VERIFIED_USERS:
        keyboard = [[InlineKeyboardButton("Show Instructions", callback_data='show_instructions')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(
            rf"Welcome back, {user.mention_html()}! You are verified and ready to go.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_html(
            rf"Hi {user.mention_html()}! This is a private bot. 🔐\n\n"
            "To gain access, you must verify yourself with a secret code.\n\n"
            "Please use the command: <code>/verify &lt;your_code&gt;</code>"
        )

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifies a user if they provide the correct secret code."""
    user = update.effective_user
    if user.id in VERIFIED_USERS:
        await update.message.reply_text("✅ You are already verified.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/verify <your_code>`")
        return

    if context.args[0] == VERIFICATION_CODE:
        VERIFIED_USERS.add(user.id)
        save_verified_users()
        logger.info(f"New user verified: {user.name} ({user.id})")
        await update.message.reply_text("🎉 Verification successful! You now have full access.")
    else:
        logger.warning(f"Failed verification attempt by {user.name} ({user.id})")
        await update.message.reply_text("❌ Incorrect verification code.")

@verified_only
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receives, downloads, and dispatches media files to the processing function."""
    message = update.message
    media_file = message.video or message.audio or message.document
    
    if not media_file:
        logger.warning("handle_media triggered but no processable media was found.")
        return
        
    # --- MODIFIED: Log the file size to help with debugging ---
    file_size_mb = round(media_file.file_size / (1024 * 1024), 2) if media_file.file_size else "Unknown"
    logger.info(f"File received from {update.effective_user.name}. Size: {file_size_mb} MB.")

    # Check if the document is a valid media type if it was sent as a document
    if message.document and not (media_file.mime_type and ('video' in media_file.mime_type or 'audio' in media_file.mime_type)):
        await message.reply_text("This bot only accepts video and audio files.")
        return

    await message.reply_text(f"Processing your file ({file_size_mb} MB)... This may take a moment for large files.")

    try:
        bot_file = await context.bot.get_file(media_file.file_id)
        
        extension = "file"
        if media_file.mime_type:
            extension = media_file.mime_type.split('/')[1]
        original_file_name = media_file.file_name or f"{media_file.file_id}.{extension}"
        
        MEDIA_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        save_path = MEDIA_SAVE_DIR / os.path.basename(original_file_name)

        logger.info(f"Starting download to: {save_path}")
        await bot_file.download_to_drive(save_path)
        logger.info(f"File downloaded successfully.")

        await process_media_file(save_path, update, context)

    except Exception as e:
        logger.error(f"Error handling media file: {e}", exc_info=True)
        await message.reply_text("❌ An error occurred while saving your file. This can happen with very large files.")

@verified_only
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button presses for verified users."""
    query = update.callback_query
    await query.answer()
    if query.data == 'show_instructions':
        instructions = "Send any audio or video file. I will save it, process it, and confirm."
        await query.edit_message_text(text=instructions)


# --- 5. Main Application Entry Point ---

def main() -> None:
    """Sets up the bot, registers handlers, and starts polling."""
    if not BOT_TOKEN or not VERIFICATION_CODE:
        logger.critical("FATAL: BOT_TOKEN or VERIFICATION_CODE not found in .env file.")
        return

    load_verified_users()

    # --- MODIFIED: Configure custom timeouts for handling large files ---
    # Set a 10-minute read timeout and a 1-minute pool timeout.
    request_settings = {
        'read_timeout': 600, 
        'connect_timeout': 10,
        'pool_timeout': 120 
    }
    httpx_request = HTTPXRequest(**request_settings)

    # Build the application with the custom request settings
    application = Application.builder().token(BOT_TOKEN).request(httpx_request).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("verify", verify_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    media_filter = filters.VIDEO | filters.AUDIO | filters.Document.ALL
    application.add_handler(MessageHandler(media_filter, handle_media))

    logger.info("Bot is running with custom timeouts...")
    application.run_polling()


if __name__ == "__main__":
    main()

def AI_integration(user_query: str) -> str:

    """
    Placeholder for AI integration logic.
    This function can be expanded to include calls to AI models or APIs.
    """
    model = "gemini-2.5-flash"
    prompt = """
    You're a specialized AI model, integrated with a bot to handle user queries.
    Your task is to understand the user's intent and provide accurate responses. If user is asking for help, provide guidance on how to use the bot.
    If the user asks for information about the bot, provide a brief description of its capabilities. 
    If the user asks for verification, remind them to use the /verify command with the correct code.
    If the user asks for media processing, inform them that they can send media files for processing.
    """