import argparse
import asyncio
import os
import sys

from mt_downloader import MTDownloader


async def main():
    parser = argparse.ArgumentParser(description="Telegram Saved Messages Backup Tool")
    parser.add_argument("--api-id", type=int, help="Telegram API ID")
    parser.add_argument("--api-hash", type=str, help="Telegram API Hash")
    parser.add_argument(
        "--session", type=str, default="mysession", help="Session file name"
    )
    parser.add_argument(
        "--path", type=str, default="./downloads", help="Download directory"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of messages to check (default: all)",
    )

    args = parser.parse_args()

    api_id = args.api_id
    api_hash = args.api_hash

    # Fallback to environment variables
    if not api_id:
        api_id = os.environ.get("TG_API_ID")
        if api_id:
            api_id = int(api_id)

    if not api_hash:
        api_hash = os.environ.get("TG_API_HASH")

    # Fallback to interactive input
    if not api_id:
        try:
            val = input("Enter Telegram API ID: ")
            api_id = int(val)
        except ValueError:
            print("Invalid API ID. Exiting.")
            sys.exit(1)

    if not api_hash:
        api_hash = input("Enter Telegram API Hash: ")
        if not api_hash:
            print("Invalid API Hash. Exiting.")
            sys.exit(1)

    downloader = MTDownloader(
        session_name=args.session, api_id=api_id, api_hash=api_hash, base_path=args.path
    )

    try:
        await downloader.start()
        print("Starting backup of Saved Messages...")
        await downloader.backup_saved_messages(limit=args.limit)
        print("Backup completed successfully.")
    except KeyboardInterrupt:
        print("\nBackup interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        await downloader.close()


if __name__ == "__main__":
    asyncio.run(main())
