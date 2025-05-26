import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, ConversationHandler, CallbackContext
)
import pysubs2
import requests
import asyncio
from openai import OpenAI
import logging.handlers
import zipfile
import shutil
from dotenv import load_dotenv

# Load environment variables from key.env file
load_dotenv('key.env')

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants - Load from environment variables
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
UPLOAD_FOLDER = "uploads"

# Validate that required environment variables are set
if not TELEGRAM_API_TOKEN:
    raise ValueError("TELEGRAM_API_TOKEN environment variable is not set")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY environment variable is not set")

# Conversation states - removed SELECTING_SOURCE
SELECTING_TARGET, AWAITING_FILE = range(2)

# Supported languages
SUPPORTED_LANGUAGES = {
    "Chinese": "中文",
    "English": "English",
    "Russian": "Русский",
    "Japanese": "日本語",
    "Korean": "한국어",
    "Spanish": "Español",
    "French": "Français",
    "German": "Deutsch"
}

# Define supported subtitle formats
SUPPORTED_FORMATS = [".ass", ".srt", ".ssa", ".sub", ".mpl", ".tmp", ".vtt"]

# Create upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# OpenAI client
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# Start conversation - directly ask for target language
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for target language."""
    # Clear any previous conversation data
    context.user_data.clear()
    
    # Create keyboard with language options
    keyboard = [[lang] for lang in SUPPORTED_LANGUAGES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "Hello! I'm a subtitle translator bot.\n\n"
        "Which language would you like to translate to?",
        reply_markup=reply_markup
    )
    
    return SELECTING_TARGET

# Handle target language selection
async def select_target_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the target language and ask for the file."""
    user_input = update.message.text
    
    # Case-insensitive language matching
    target_language = None
    
    # Try exact case first
    if user_input in SUPPORTED_LANGUAGES:
        target_language = user_input
    else:
        # Try case-insensitive matching
        for language in SUPPORTED_LANGUAGES:
            if language.lower() == user_input.lower():
                target_language = language
                break
    
    # Add common language abbreviations/variations
    language_aliases = {
        "eng": "English",
        "en": "English",
        "chi": "Chinese",
        "cn": "Chinese",
        "zh": "Chinese",
        "中文": "Chinese",
        "rus": "Russian",
        "ru": "Russian",
        "jp": "Japanese",
        "ja": "Japanese",
        "日本語": "Japanese",
        "kor": "Korean",
        "ko": "Korean",
        "한국어": "Korean",
        "spa": "Spanish",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "ger": "German"
    }
    
    # Check aliases if not found by direct matching
    if target_language is None and user_input.lower() in language_aliases:
        target_language = language_aliases[user_input.lower()]
    
    # Validate language selection
    if target_language is None:
        await update.message.reply_text(
            f"Sorry, I don't recognize '{user_input}' as a supported language. Please select from the options."
        )
        return SELECTING_TARGET
    
    # Save the target language
    context.user_data['target_language'] = target_language
    
    await update.message.reply_text(
        f"Perfect! I'll translate your subtitles to {target_language}.\n"
        f"The source language will be automatically detected.\n\n"
        "Please send me your subtitle file. I support .ass, .srt, .ssa, .sub, .mpl, .tmp and .vtt formats.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return AWAITING_FILE

# Handle file upload
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the subtitle file."""
    # Get target language
    target_language = context.user_data.get('target_language')
    
    if not target_language:
        await update.message.reply_text(
            "Sorry, I couldn't determine your target language. Please start again with /start."
        )
        return ConversationHandler.END
    
    # Get the file
    message = update.message
    file = message.document
    
    # Check if it's a supported subtitle file
    file_ext = os.path.splitext(file.file_name)[1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        await message.reply_text(
            "Please send a supported subtitle file. I support these formats:\n"
            "• .ass (Advanced SubStation Alpha)\n"
            "• .srt (SubRip)\n" 
            "• .ssa (SubStation Alpha)\n"
            "• .sub (MicroDVD)\n"
            "• .mpl (MPL2)\n"
            "• .tmp (TMP)\n"
            "• .vtt (WebVTT)"
        )
        return AWAITING_FILE
    
    # Notify user we're processing
    status_message = await message.reply_text(
        f"Processing your subtitle file...\n"
        f"Translating to {target_language}.\n"
        f"This may take a few minutes."
    )
    
    # Track files to clean up
    file_path = None
    translated_file_path = None
    zip_path = None
    
    # Download file
    try:
        file_obj = await file.get_file()
        user_id = str(update.effective_user.id)
        user_folder = os.path.join(UPLOAD_FOLDER, user_id)
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, file.file_name)
        
        # Save file path in context for potential cancellation
        context.user_data['file_path'] = file_path
        context.user_data['user_folder'] = user_folder
        
        await asyncio.wait_for(
            file_obj.download_to_drive(custom_path=file_path),
            timeout=30
        )
        
        # Update status
        await status_message.edit_text(
            f"File downloaded successfully.\n"
            f"Now translating to {target_language}...\n\n"
            f"⏱️ This translation will take a few minutes. Please be patient."
        )
        
    except asyncio.TimeoutError:
        await message.reply_text("File download timed out. Please try again with a smaller file.")
        await cleanup_files(context)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await message.reply_text("Error downloading file. Please try again.")
        await cleanup_files(context)
        return ConversationHandler.END
    
    # Process and translate file
    try:
        # Parse subtitles
        file_ext = os.path.splitext(file_path)[1].lower()
        # Strip the dot from extension
        subtitle_format = file_ext[1:] 
        subs = pysubs2.load(file_path, format=subtitle_format)
        
        # Extract text
        text_chunks = []
        line_map = {}
        chunk_index = 0

        # Only extract non-empty text and maintain a mapping
        for i, event in enumerate(subs.events):
            if event.text and event.text.strip():
                text_chunks.append(event.text)
                line_map[chunk_index] = i
                chunk_index += 1

        # Join only non-empty chunks for translation
        text_to_translate = "\n".join(text_chunks)
        
        # Translate - removed source_language parameter
        translated_text = await translate_text(
            text_to_translate, 
            target_language
        )
        
        # Update status
        await status_message.edit_text(
            f"Translation complete!\n"
            f"Processing subtitle file... (0%)"
        )
        
        # After translation, use the line map for efficient reassignment
        translated_lines = translated_text.split("\n")
        for chunk_idx, event_idx in line_map.items():
            if chunk_idx < len(translated_lines):
                subs.events[event_idx].text = translated_lines[chunk_idx]
        
        # Save translated file
        translated_file_path = os.path.join(
            user_folder, f"{target_language}_{file.file_name}"
        )
        context.user_data['translated_file_path'] = translated_file_path
        
        subs = add_font_fallbacks(subs, target_language)
        subs.save(translated_file_path, format=subtitle_format)
        
        # For large files, compress before sending
        if os.path.getsize(translated_file_path) > 10_000_000:  # 10MB
            zip_path = f"{translated_file_path}.zip"
            context.user_data['zip_path'] = zip_path
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(translated_file_path, os.path.basename(translated_file_path))
            
            await message.reply_document(
                document=open(zip_path, "rb"),
                filename=f"{os.path.basename(translated_file_path)}.zip",
                caption="File was compressed due to large size"
            )
        else:
            await message.reply_document(
                document=open(translated_file_path, "rb"),
                filename=os.path.basename(translated_file_path),
            )
        
        # Final success message
        await status_message.edit_text(
            f"✅ Translation to {target_language} completed successfully!"
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await status_message.edit_text(
            f"❌ Error during translation: {str(e)}\n"
            "Please try again later or contact support."
        )
    
    finally:
        # Clean up files immediately
        await cleanup_files(context)
    
    # End conversation
    await message.reply_text(
        "Translation process complete. Start a new translation with /start."
    )
    return ConversationHandler.END

# Helper function to clean up files
async def cleanup_files(context: ContextTypes.DEFAULT_TYPE):
    """Clean up user-specific temporary files"""
    files_to_delete = [
        context.user_data.get('file_path'),
        context.user_data.get('translated_file_path'),
        context.user_data.get('zip_path')
    ]
    
    for file_path in files_to_delete:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")
    
    # Only clean user-specific folder, not entire upload directory
    user_folder = context.user_data.get('user_folder')
    if user_folder and os.path.exists(user_folder) and os.path.isdir(user_folder):
        try:
            shutil.rmtree(user_folder)
            logger.info(f"Cleaned user folder: {user_folder}")
        except Exception as e:
            logger.error(f"Error cleaning user folder: {e}")
    
    # Clear file paths from user data
    if 'file_path' in context.user_data:
        del context.user_data['file_path']
    if 'translated_file_path' in context.user_data:
        del context.user_data['translated_file_path']
    if 'zip_path' in context.user_data:
        del context.user_data['zip_path']
    if 'user_folder' in context.user_data:
        del context.user_data['user_folder']

# Translation function - modified to auto-detect source language
async def translate_text(text: str, target_language: str) -> str:
    """Translate text using DeepSeek API with automatic source language detection."""
    # Create system prompt for auto-detection
    system_prompt = f"""
You are a professional subtitle translator. Follow these rules:
1. Automatically detect the source language and translate text to {target_language}
2. Preserve ALL formatting tags like {{\\an8}}, {{\\fnArial}}, etc.
3. Keep exact line breaks and timestamps
4. Never modify numbers or timecodes
5. Maintain original text structure
6. Preserve any special characters or symbols

Example input: 
{{\\an8}}Hello world

Example output:
{{\\an8}}[Translated text in {target_language}]
"""
    
    # Run API call in a separate thread
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.3  # Lower for more consistent translations
        ).choices[0].message.content
    )

# Enhanced cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation, cleaning up any files."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    
    # Clean up any temporary files
    await cleanup_files(context)
    
    # Clear all user data
    context.user_data.clear()
    
    await update.message.reply_text(
        "Translation cancelled. All temporary files have been deleted.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# Add this function to help with font compatibility
def add_font_fallbacks(subs, target_language):
    """Add appropriate font fallbacks based on target language"""
    
    # Define language-specific fallback fonts
    fallbacks = {
        "Chinese": "SimSun, Arial",
        "Japanese": "MS Gothic, Yu Gothic, Arial",
        "Korean": "Malgun Gothic, Arial",
        "Russian": "Arial, Tahoma",
        # Add others as needed
    }
    
    # Only modify if target language has specific fallbacks
    if target_language in fallbacks:
        # Add fallback to style section if needed
        for style in subs.styles.values():
            if not "," in style.fontname:  # Only modify if no fallbacks already specified
                style.fontname = f"{style.fontname}, {fallbacks[target_language]}"
    
    return subs

# Main function
def main() -> None:
    """Set up and run the bot."""
    # Filter out getUpdates spam
    class GetUpdatesFilter(logging.Filter):
        def filter(self, record):
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                if 'HTTP Request: POST' in record.msg and '/getUpdates' in record.msg:
                    return False
            return True
    
    # Apply filter
    logging.getLogger('httpx').addFilter(GetUpdatesFilter())
    
    # Create application
    application = Application.builder() \
        .token(TELEGRAM_API_TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .build()
    
    # Set up conversation handler with cancel command available in all states
    # Removed SELECTING_SOURCE state
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_target_language),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_FILE: [
                MessageHandler(filters.Document.ALL, handle_file),
                CommandHandler('cancel', cancel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    
    # Add standalone help command - updated to reflect simpler flow
    application.add_handler(CommandHandler("help", lambda update, context: 
        update.message.reply_text(
            "How to use this bot:\n"
            "1. Type /start to begin a new translation\n"
            "2. Select target language\n"
            "3. Send your subtitle file (.ass, .srt, .ssa, .sub, .mpl, .tmp, .vtt)\n"
            "4. Wait for translation to complete\n\n"
            "Type /cancel to stop the current process at any time. All temporary files will be deleted."
        )
    ))
    
    # Add error handler
    async def error_handler(update, context):
        logger.error(msg="Exception while handling update:", exc_info=context.error)
        if update and update.message:
            await update.message.reply_text("Sorry, an error occurred. Please try again.")
        
        # Clean up any files in case of error
        await cleanup_files(context)
    
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("Starting language translation bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()