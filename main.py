import argparse
import asyncio
import os
import sys

from mt_downloader import MTDownloader


async def main():
    parser = argparse.ArgumentParser(description="Telegram Saved Messages Backup Tool")
    parser.add_argument("--api-id", type=int, help="Telegram API ID")
    parser.add_argument("--api-hash", type=str, help="Telegram API Hash")
    parser.add_argument("--phone", type=str, help="Phone number with country code")
    parser.add_argument(
        "--session", type=str, default="saved_forever", help="Session file name"
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
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Ignore state file and start from scratch",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Only generate HTML from existing downloads",
    )
    parser.add_argument(
        "--telegraph-download-js",
        action="store_true",
        help="DANGER: Download JavaScript for Telegraph pages. This is HIGHLY LIKELY to break local page layout and functionality. Use only for debugging.",
    )

    args = parser.parse_args()

    if args.html_only:
        from html_generator import generate_html
        generate_html(args.path)
        return

    api_id = args.api_id
    api_hash = args.api_hash

    # Fallback to environment variables
    if not api_id:
        api_id = os.environ.get("TG_API_ID")
        if api_id:
            api_id = int(api_id)

    if not api_hash:
        api_hash = os.environ.get("TG_API_HASH")

    # Fallback to interactive input if not provided
    if not api_id:
        try:
            val = input("Enter Telegram API ID: ")
            api_id = int(val)
        except ValueError:
            print("Invalid API ID. Exiting.")
            sys.exit(1)

    if not api_hash:
        api_hash = input("Enter Telegram API Hash: ").strip()
        if not api_hash:
            print("Invalid API Hash. Exiting.")
            sys.exit(1)

    phone = args.phone
    if not phone and not os.path.exists(f"{args.session}.session"):
        phone = input("Enter phone number (e.g., +123456789): ").strip()

    downloader = MTDownloader(
        session_name=args.session,
        api_id=api_id,
        api_hash=api_hash,
        base_path=args.path,
        download_js=args.telegraph_download_js,
    )
    
    if args.reset_state:
        downloader.last_msg_id = 0

    try:
        await downloader.start(phone=phone)
        print("Starting backup of Saved Messages...")
        await downloader.backup_saved_messages(limit=args.limit)
        print("Backup completed successfully.")
        
        from html_generator import generate_html
        generate_html(args.path)
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
