# Telegram Saved Messages Backup Tool

A Python CLI tool to backup your Telegram "Saved Messages" chat. It downloads text messages, media (photos, videos, documents), and content from Telegraph links.

## Features

- **Authentication**: Connects via Telegram API (requires API ID and Hash).
- **Incremental Backup**: Checks for existing files to avoid re-downloading.
- **Media Support**: Downloads Photos, Videos, Documents.
- **Telegraph Support**: Parses and downloads content from `telegra.ph` links.
- **Linked Messages**: Recursively parses and downloads messages linked (e.g., `t.me/c/...`) within your saved messages.
- **Forwarded Messages**: Preserves forward metadata and downloads content.
- **Progress Bars**: Visual feedback for message processing and file downloads.

## Prerequisites

- Python 3.8+
- Telegram API Credentials: Get your `api_id` and `api_hash` from [https://my.telegram.org/apps](https://my.telegram.org/apps).

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install telethon aiohttp aiofiles beautifulsoup4 tqdm
   ```

## Usage

Run the tool using `main.py`. You can provide credentials via arguments, environment variables, or interactive input.

### Command Line Arguments

```bash
python main.py --api-id <YOUR_API_ID> --api-hash <YOUR_API_HASH> --path <DOWNLOAD_PATH>
```

- `--api-id`: Your Telegram API ID.
- `--api-hash`: Your Telegram API Hash.
- `--session`: Session file name (default: "mysession").
- `--path`: Directory to save downloads (default: "./downloads").
- `--limit`: Number of messages to process (default: all).

### Environment Variables

You can set `TG_API_ID` and `TG_API_HASH` in your environment to avoid passing them as arguments.

```bash
export TG_API_ID=123456
export TG_API_HASH=abcdef...
python main.py
```

### Interactive Mode

If you run `python main.py` without arguments, it will prompt you for the API ID and Hash.

## Output Structure

Files are saved in the specified download directory with the following naming convention:
- `{message_id}_meta.json`: JSON file containing message text and metadata.
- `{message_id}_media.ext`: Downloaded media file.
- `{message_id}_telegraph.html`: Telegraph page content.
- `{message_id}_telegraph_img_X.ext`: Telegraph page images.
- `linked_{original_id}_...`: Content from linked messages.

## Notes

- The first time you run it, you will be asked to enter your phone number and the code sent to your Telegram account to authenticate.
- The session is saved locally (e.g., `mysession.session`), so subsequent runs won't require re-login.
