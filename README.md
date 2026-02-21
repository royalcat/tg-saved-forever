# Telegram Saved Messages Backup Tool

This tool allows you to backup your Telegram "Saved Messages" chat to your local machine. It saves text, media, Telegraph pages, and follows links to other messages.

## Features

- **Resume-ability**: Tracks the last downloaded message to avoid duplicate downloads.
- **Media Download**: Downloads all media files with a progress bar.
- **Telegraph Backup**: Downloads Telegraph pages and their images for offline viewing.
- **Link Parsing**: Automatically fetches and downloads content from `t.me/...` links found in your messages.
- **Organized Storage**: Each message is stored in its own folder with metadata and files.

## Installation

1.  Clone the repository or download the files.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  Get your **API ID** and **API Hash** from [my.telegram.org](https://my.telegram.org).
2.  Run the script:
    ```bash
    python main.py --api-id YOUR_ID --api-hash YOUR_HASH --phone +YOUR_PHONE
    ```

### Command Line Arguments

- `--api-id`: Your Telegram API ID.
- `--api-hash`: Your Telegram API Hash.
- `--phone`: Your phone number in international format (e.g., +123456789).
- `--path`: Directory where data will be saved (default: `./downloads`).
- `--limit`: Max number of messages to process.
- `--session`: Custom session name (default: `saved_forever`).
- `--reset-state`: Start from the very first message regardless of previous progress.

## Storage Format

Downloads are organized by message ID:
```
downloads/
  .state.json           # Tracks progress
  101/
    meta.json           # JSON metadata (date, chat_id, text, etc.)
    message.txt         # Plain text message
    photo.jpg           # Downloaded media
    telegraph_0/        # Local copy of a Telegraph link
      index.html
      images/
        ...
```
