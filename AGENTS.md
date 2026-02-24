# Project: Telegram Saved Messages Backup

## Core Functionality
- **Authentication**: Uses Telethon (user agent) to authenticate.
- **Incremental Backup**: Tracks `last_msg_id` in `.state.json` to resume from the last message.
- **Media Deduplication**: Tracks media `access_hash` values in `.media_hashes.json` to avoid re-downloading identical files. Duplicate media is copied using CoW reflinks (on btrfs/xfs) with automatic fallback to regular copy.
- **Session Fingerprint**: Stores an SHA-256 hash of the session auth key. On session change, the media dedup index is automatically invalidated and rebuilt during the next backup pass (existing files are kept, only the index is cleared).
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
- Media dedup index keys are `doc:<id>:<access_hash>` or `photo:<id>:<access_hash>`, scoped to the current session. The `access_hash` is unique per account/session, so the index is invalidated when the auth key changes.
- Reflink copy (`FICLONE` ioctl) is attempted first on Linux; falls back to `shutil.copy2` on unsupported filesystems or platforms.
- The media index is saved alongside state after each message to survive interruptions.


# Make sure to update memory when new features or limitations are stated by the User
