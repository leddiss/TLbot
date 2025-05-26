# Subtitle Translator Bot

A Telegram bot that automatically translates subtitle files between different languages using AI.

## Features

- 🌍 Supports multiple subtitle formats: `.ass`, `.srt`, `.ssa`, `.sub`, `.mpl`, `.tmp`, `.vtt`
- 🤖 Automatic source language detection
- 🗣️ Translates to: Chinese, English, Russian, Japanese, Korean, Spanish, French, German
- ⏱️ Preserves subtitle formatting and timing
- 📦 Handles large files with automatic compression
- 🔒 Secure API key management

## Prerequisites

- Python 3.7 or higher
- A Telegram account
- API keys (see setup instructions below)

## Setup

### 1. Clone or Download

Download this repository or clone it:
```bash
git clone <your-repo-url>
cd subtitle-translator-bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Get API Keys

You'll need two API keys:

#### Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the instructions
3. Copy the bot token you receive

#### DeepSeek API Key
1. Sign up at [DeepSeek Platform](https://platform.deepseek.com/)
2. Navigate to API Keys section
3. Create a new API key
4. Copy the key

### 4. Configure Environment Variables

1. Copy the template file:
   ```bash
   cp key.env.template key.env
   ```

2. Edit `key.env` and replace the placeholder values with your actual API keys:
   ```
   TELEGRAM_API_TOKEN=your_actual_telegram_bot_token
   DEEPSEEK_API_KEY=your_actual_deepseek_api_key
   ```

### 5. Run the Bot

```bash
python subtitle_translator.py
```

You should see: "Starting language translation bot..."

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to begin a new translation
3. Select your target language from the keyboard
4. Upload your subtitle file
5. Wait for the translation to complete (this may take a few minutes)
6. Download the translated file

## Supported Commands

- `/start` - Begin a new translation session
- `/cancel` - Cancel the current operation and clean up files
- `/help` - Show help information

## Supported Languages

- **Chinese** (中文)
- **English**
- **Russian** (Русский)
- **Japanese** (日本語)
- **Korean** (한국어)
- **Spanish** (Español)
- **French** (Français)
- **German** (Deutsch)

## File Format Support

| Format | Extension | Description |
|--------|-----------|-------------|
| ASS | `.ass` | Advanced SubStation Alpha |
| SRT | `.srt` | SubRip |
| SSA | `.ssa` | SubStation Alpha |
| SUB | `.sub` | MicroDVD |
| MPL | `.mpl` | MPL2 |
| TMP | `.tmp` | TMP |
| VTT | `.vtt` | WebVTT |

## Security Notes

⚠️ **Important Security Information:**

- **Never commit your `key.env` file to version control!**
- Keep your API keys private and secure
- The `key.env` file is already included in `.gitignore` for your protection
- If you accidentally expose your keys, regenerate them immediately

## Troubleshooting

### Common Issues

1. **"Environment variable not set" error**
   - Make sure you've created the `key.env` file
   - Check that your API keys are correctly formatted (no extra spaces)

2. **Bot doesn't respond**
   - Verify your Telegram bot token is correct
   - Make sure the bot is not already running elsewhere

3. **Translation fails**
   - Check your DeepSeek API key and account credits
   - Ensure you have an active internet connection

4. **File upload issues**
   - Make sure your file is in a supported format
   - Check that the file size is reasonable (under 20MB recommended)

### Getting Help

If you encounter issues:
1. Check the console output for error messages
2. Verify your API keys are valid
3. Ensure all dependencies are installed correctly

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## License

This project is open source and available under the MIT License.

## Disclaimer

This bot uses third-party APIs (Telegram and DeepSeek). Please review their terms of service and pricing before use. Translation quality depends on the AI service and may vary. 