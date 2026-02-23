# Project: Telegram Saved Messages Backup

## Core Functionality
- **Authentication**: Uses Telethon (user agent) to authenticate.
- **Incremental Backup**: Tracks `last_msg_id` in `.state.json` to resume from the last message.
- **Storage**: Data is saved in `./downloads/` as plain files (JSON, TXT, and media) organized by message ID.
- **HTML Backup**: Automatically generates a chat-like HTML interface (`index.html` in the downloads folder) to browse messages and media offline.
- **Rich Media**: Supports downloading standard media, Telegraph pages (with images), and following `t.me` message links.

## Tech Stack
- **Language**: Python
- **Library**: Telethon (Telegram API)
- **Async**: `aiohttp`, `aiofiles`, `asyncio`
- **Scraping**: `BeautifulSoup4` (for Telegraph)
- **CLI**: `argparse`, `tqdm` (progress bars)

## Architectural Decisions
- Each message is isolated in its own folder to ensure metadata and associated media are clearly linked.
- Linked messages (from `t.me` links) are stored as sub-folders of the parent message to maintain context.


# Make sure to update memory when new features or limitations are stated by the User
