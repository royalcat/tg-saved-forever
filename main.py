import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import cast

from mt_downloader import MTDownloader


@dataclass
class AppConfig:
    """Typed container for parsed CLI arguments."""

    session_name: str
    download_path: str
    api_id: int
    api_hash: str
    html_only: bool
    telegraph_download_js: bool
    reset_state: bool
    limit: int | None
    phone: str | None


def _parse_args() -> AppConfig:
    """Parse CLI arguments and return typed config."""
    parser = argparse.ArgumentParser(description="Telegram Saved Messages Backup Tool")
    _ = parser.add_argument("--api-id", type=int, help="Telegram API ID")
    _ = parser.add_argument("--api-hash", type=str, help="Telegram API Hash")
    _ = parser.add_argument("--phone", type=str, help="Phone number with country code")
    _ = parser.add_argument(
        "--session", type=str, default="saved_forever", help="Session file name"
    )
    _ = parser.add_argument(
        "--path", type=str, default="./downloads", help="Download directory"
    )
    _ = parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of messages to check (default: all)",
    )
    _ = parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Ignore state file and start from scratch",
    )
    _ = parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML from existing downloads",
    )
    _ = parser.add_argument(
        "--telegraph-download-js",
        action="store_true",
        help="DANGER: Download JavaScript for Telegraph pages. This is HIGHLY LIKELY to break local page layout and functionality. Use only for debugging.",
    )

    ns = parser.parse_args()

    session_name = cast(str, getattr(ns, "session"))
    download_path = cast(str, getattr(ns, "path"))
    html_only = cast(bool, getattr(ns, "html_only"))
    telegraph_download_js = cast(bool, getattr(ns, "telegraph_download_js"))
    reset_state = cast(bool, getattr(ns, "reset_state"))
    arg_limit = cast("int | None", getattr(ns, "limit"))
    phone = cast("str | None", getattr(ns, "phone"))

    # Resolve api_id
    api_id: int | None = cast("int | None", getattr(ns, "api_id"))
    if not api_id:
        env_api_id = os.environ.get("TG_API_ID")
        if env_api_id:
            api_id = int(env_api_id)
    if not api_id:
        try:
            val = input("Enter Telegram API ID: ")
            api_id = int(val)
        except ValueError:
            print("Invalid API ID. Exiting.")
            sys.exit(1)

    # Resolve api_hash
    api_hash: str | None = cast("str | None", getattr(ns, "api_hash"))
    if not api_hash:
        api_hash = os.environ.get("TG_API_HASH")
    if not api_hash:
        api_hash = input("Enter Telegram API Hash: ").strip()
        if not api_hash:
            print("Invalid API Hash. Exiting.")
            sys.exit(1)

    # Resolve phone
    if not phone and not os.path.exists(f"{session_name}.session"):
        phone = input("Enter phone number (e.g., +123456789): ").strip()

    return AppConfig(
        session_name=session_name,
        download_path=download_path,
        api_id=api_id,
        api_hash=api_hash,
        html_only=html_only,
        telegraph_download_js=telegraph_download_js,
        reset_state=reset_state,
        limit=arg_limit,
        phone=phone,
    )


async def main() -> None:
    config = _parse_args()

    if config.html_only:
        from html_generator import generate_html

        generate_html(config.download_path)
        return

    downloader = MTDownloader(
        session_name=config.session_name,
        api_id=config.api_id,
        api_hash=config.api_hash,
        base_path=config.download_path,
        telegraph_download_js=config.telegraph_download_js,
    )

    if config.reset_state:
        downloader.last_msg_id = 0

    try:
        await downloader.start(phone=config.phone)
        print("Starting backup of Saved Messages...")
        await downloader.backup_saved_messages(limit=config.limit)
        print("Backup completed successfully.")

        from html_generator import generate_html

        generate_html(config.download_path)
    except KeyboardInterrupt:
        print("\nBackup interrupted by user.")
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"\nAn error occurred: {e}")
    finally:
        await downloader.close()


if __name__ == "__main__":
    asyncio.run(main())
