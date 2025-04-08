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

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
TELEGRAM_API_TOKEN = "7627545759:AAE2NmH-ci8RE1ILwvN2teS2SYx91705F_A"
DEEPSEEK_API_KEY = "sk-5f6ab3a5c46b4bd499cd5e8cb928ab75"
UPLOAD_FOLDER = "uploads"

# Conversation states
SELECTING_SOURCE, SELECTING_TARGET, AWAITING_FILE = range(3)

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

# Create upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# OpenAI client
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# Start conversation
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for source language."""
    # Clear any previous conversation data
    context.user_data.clear()
    
    # Create keyboard with language options
    keyboard = [[lang] for lang in SUPPORTED_LANGUAGES.keys()]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "Hello! I'm a subtitle translator bot. Let's set up your translation.\n\n"
        "First, which language are we translating FROM?",
        reply_markup=reply_markup
    )
    
    return SELECTING_SOURCE

# Handle source language selection
async def select_source_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the source language and ask for target language."""
    source_language = update.message.text
    
    # Validate language selection
    if source_language not in SUPPORTED_LANGUAGES:
        await update.message.reply_text(
            f"Sorry, I don't support '{source_language}'. Please select from the options."
        )
        return SELECTING_SOURCE
    
    # Save the source language
    context.user_data['source_language'] = source_language
    
    # Create keyboard for target language
    # Remove source language from options
    target_options = [lang for lang in SUPPORTED_LANGUAGES.keys() 
                     if lang != source_language]
    keyboard = [[lang] for lang in target_options]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"Great! We'll translate from {source_language}.\n\n"
        "Now, which language would you like to translate TO?",
        reply_markup=reply_markup
    )
    
    return SELECTING_TARGET

# Handle target language selection
async def select_target_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the target language and ask for the file."""
    target_language = update.message.text
    source_language = context.user_data.get('source_language')
    
    # Validate language selection
    if target_language not in SUPPORTED_LANGUAGES:
        await update.message.reply_text(
            f"Sorry, I don't support '{target_language}'. Please select from the options."
        )
        return SELECTING_TARGET
    
    # Save the target language
    context.user_data['target_language'] = target_language
    
    await update.message.reply_text(
        f"Perfect! I'll translate from {source_language} to {target_language}.\n\n"
        "Please send me your .ass subtitle file now.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return AWAITING_FILE

# Handle file upload
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the subtitle file."""
    # Get source and target languages
    source_language = context.user_data.get('source_language')
    target_language = context.user_data.get('target_language')
    
    if not source_language or not target_language:
        await update.message.reply_text(
            "Sorry, I couldn't determine your language preferences. Please start again with /start."
        )
        return ConversationHandler.END
    
    # Get the file
    message = update.message
    file = message.document
    
    # Check if it's an .ass file
    if not file.file_name.lower().endswith(".ass"):
        await message.reply_text(
            "Please send a .ass subtitle file. Other formats are not supported yet."
        )
        return AWAITING_FILE
    
    # Notify user we're processing
    status_message = await message.reply_text(
        f"Processing your subtitle file...\n"
        f"Translating from {source_language} to {target_language}.\n"
        f"This may take a few minutes."
    )
    
    # Download file
    try:
        file_obj = await file.get_file()
        file_path = os.path.join(UPLOAD_FOLDER, file.file_name)
        
        await asyncio.wait_for(
            file_obj.download_to_drive(custom_path=file_path),
            timeout=30
        )
        
        # Update status
        await status_message.edit_text(
            f"File downloaded successfully.\n"
            f"Now translating from {source_language} to {target_language}..."
        )
        
    except asyncio.TimeoutError:
        await message.reply_text("File download timed out. Please try again with a smaller file.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await message.reply_text("Error downloading file. Please try again.")
        return ConversationHandler.END
    
    # Process and translate file
    try:
        # Parse subtitles
        subs = pysubs2.load(file_path, format='ass')
        
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
        
        # Translate
        translated_text = await translate_text(
            text_to_translate, 
            source_language, 
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
            UPLOAD_FOLDER, f"{target_language}_{file.file_name}"
        )
        subs = add_font_fallbacks(subs, target_language)
        subs.save(translated_file_path, format='ass')
        
        # For large files, compress before sending
        if os.path.getsize(translated_file_path) > 10_000_000:  # 10MB
            zip_path = f"{translated_file_path}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(translated_file_path, os.path.basename(translated_file_path))
            
            await message.reply_document(
                document=open(zip_path, "rb"),
                filename=f"{os.path.basename(translated_file_path)}.zip",
                caption="File was compressed due to large size"
            )
            os.remove(zip_path)
        else:
            await message.reply_document(
                document=open(translated_file_path, "rb"),
                filename=os.path.basename(translated_file_path),
            )
        
        # Final success message
        await status_message.edit_text(
            f"✅ Translation from {source_language} to {target_language} completed successfully!"
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        await status_message.edit_text(
            f"❌ Error during translation: {str(e)}\n"
            "Please try again later or contact support."
        )
    
    finally:
        # Clean up files
        if os.path.exists(file_path):
            os.remove(file_path)
        if 'translated_file_path' in locals() and os.path.exists(translated_file_path):
            os.remove(translated_file_path)
    
    # End conversation
    await message.reply_text(
        "Translation process complete. Start a new translation with /start."
    )
    return ConversationHandler.END

# Translation function
async def translate_text(text: str, source_language: str, target_language: str) -> str:
    """Translate text using DeepSeek API."""
    # Create system prompt based on selected languages
    system_prompt = f"""
You are a professional subtitle translator. Follow these rules:
1. Translate {source_language} text to {target_language}
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

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    await update.message.reply_text(
        "Translation setup cancelled. Send /start to begin again.",
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
    
    # Set up conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_source_language)],
            SELECTING_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_target_language)],
            AWAITING_FILE: [MessageHandler(filters.Document.ALL, handle_file)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    
    # Add standalone help command
    application.add_handler(CommandHandler("help", lambda update, context: 
        update.message.reply_text(
            "How to use this bot:\n"
            "1. Type /start to begin a new translation\n"
            "2. Select source language\n"
            "3. Select target language\n"
            "4. Send your .ass subtitle file\n"
            "5. Wait for translation to complete\n\n"
            "Type /cancel to stop the current process."
        )
    ))
    
    # Add error handler
    async def error_handler(update, context):
        logger.error(msg="Exception while handling update:", exc_info=context.error)
        if update and update.message:
            await update.message.reply_text("Sorry, an error occurred. Please try again.")
    
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("Starting language translation bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()