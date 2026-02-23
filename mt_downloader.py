import asyncio
import io
import json
import os
import re
import shutil
import uuid
from typing import Optional

import aiofiles
import aiohttp
from bs4 import BeautifulSoup as bs
from telethon import TelegramClient
from telethon.tl.types import (
    Message,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
    WebPage,
)
from tqdm.asyncio import tqdm

mobile_device = {
    "device_model": "Pixel 6",
    "system_version": "15",
    "app_version": "12.4.0",
    "lang_code": "en",
    "system_lang_code": "en-US",
}


class MTDownloader:
    def __init__(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        base_path: str = "./downloads",
        download_js: bool = False,
    ):
        self.client = TelegramClient(
            session_name,
            api_id,
            api_hash,
            device_model=mobile_device["device_model"],
            system_version=mobile_device["system_version"],
            app_version=mobile_device["app_version"],
            lang_code=mobile_device["lang_code"],
            system_lang_code=mobile_device["system_lang_code"],
        )
        self.session = None  # Initialized in start()
        self.base_path = base_path
        self.download_js = download_js
        self.state_file = os.path.join(self.base_path, ".state.json")
        os.makedirs(self.base_path, exist_ok=True)
        self.last_msg_id = self._load_state()

    def _load_state(self) -> int:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f).get("last_msg_id", 0)
            except Exception:
                pass
        return 0

    def _save_state(self):
        tmp_state_file = self.state_file + ".tmp"
        try:
            with open(tmp_state_file, "w") as f:
                json.dump({"last_msg_id": self.last_msg_id}, f)
            os.replace(tmp_state_file, self.state_file)
        except Exception:
            if os.path.exists(tmp_state_file):
                os.remove(tmp_state_file)
            raise

    async def start(self, phone: Optional[str] = None):
        print("Attempting to connect to Telegram...")
        await self.client.start(phone=phone)
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        await self.client.disconnect()
        if self.session:
            await self.session.close()

    async def backup_saved_messages(self, limit: Optional[int] = None):
        """Backups messages from 'Saved Messages'."""
        me = await self.client.get_me()
        print(f"Connected as {me.username or me.first_name}")

        print(f"Checking for messages newer than ID: {self.last_msg_id}")

        # Create the iterator
        it = self.client.iter_messages(
            "me", min_id=self.last_msg_id, limit=limit, reverse=True
        )

        pbar = tqdm(desc="Backing up", unit="msg")

        # Iterate and process immediately to prevent file reference expiration
        async for message in it:
            pbar.total = it.total
            # Update progress bar description with dynamic message info
            msg_date = message.date.strftime("%Y-%m-%d") if message.date else "Unknown"
            pbar.set_description(f"Msg {message.id} ({msg_date})")

            # Process the message immediately
            await self._process_message(message)

            if message.id > self.last_msg_id:
                self.last_msg_id = message.id
                self._save_state()

            pbar.update(1)

        pbar.close()

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        # 1. Fix protocol (handle common parsing errors like tps://)
        if url.startswith("tps://"):
            url = "https://" + url[6:]
        elif url.startswith("http://"):
            url = "https://" + url[7:]
        elif not url.startswith("http"):
            url = "https://" + url

        # 2. Standardize case for hostname and strip trailing slash
        # (Telegra.ph URLs are usually case-insensitive, but we stay safe)
        url = url.rstrip("/")

        # 3. Strip redundant tracking parameters if any (basic check)
        if "?" in url:
            base, query = url.split("?", 1)
            # You could filter query params here if needed
            url = base

        return url

    async def _process_message(self, message: Message, depth: int = 0):
        if depth > 2:  # Prevent deep recursion
            return

        msg_folder = os.path.join(self.base_path, str(message.id))
        if depth > 0:
            msg_folder = os.path.join(msg_folder, f"linked_{message.id}")

        os.makedirs(msg_folder, exist_ok=True)

        # 1. Save Meta/Text
        await self._save_text(message, msg_folder)

        # 2. Save Media
        if message.media:
            await self._save_media(message, msg_folder)

        # 3. Check for Telegraph links
        telegraph_urls = set()
        if message.entities:
            for entity in message.entities:
                url = None
                if isinstance(entity, MessageEntityTextUrl):
                    url = entity.url
                elif isinstance(entity, MessageEntityUrl):
                    # For plain URLs, we need to extract from text
                    url = message.text[entity.offset : entity.offset + entity.length]

                if url and "telegra.ph" in url:
                    telegraph_urls.add(self._normalize_url(url))

        # Also check message.media.webpage
        if isinstance(message.media, MessageMediaWebPage) and isinstance(
            message.media.webpage, WebPage
        ):
            wp_url = message.media.webpage.url
            if wp_url and "telegra.ph" in wp_url:
                telegraph_urls.add(self._normalize_url(wp_url))

        for i, url in enumerate(telegraph_urls):
            await self._download_telegraph(
                os.path.join(msg_folder, f"telegraph_{i}"), url
            )

        # 4. Process Message Links (t.me/...)
        await self._process_links(message, depth)

    async def _process_links(self, message: Message, depth: int):
        if not message.text:
            return

        # Improved regex for telegram message links
        link_pattern = re.compile(
            r"(?:https?://)?t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)"
        )
        matches = link_pattern.findall(message.text)

        for match in matches:
            channel_id_str, username, msg_id_str = match
            msg_id = int(msg_id_str)

            peer = None
            if channel_id_str:
                try:
                    # Private channels in Telethon need to be prefixed with -100 if only digits
                    peer = int(f"-100{channel_id_str}")
                except ValueError:
                    continue
            else:
                peer = username

            try:
                fetched_msgs = await self.client.get_messages(peer, ids=[msg_id])
                if fetched_msgs and fetched_msgs[0]:
                    # We process linked messages within the SAME folder or a subfolder?
                    # Let's put linked content in a subfolder of the original message
                    parent_folder = os.path.join(self.base_path, str(message.id))
                    await self._process_linked_message(
                        fetched_msgs[0], parent_folder, depth + 1
                    )
            except Exception as e:
                # print(f"Failed to fetch linked message {peer}/{msg_id}: {e}")
                pass

    async def _process_linked_message(
        self, message: Message, parent_folder: str, depth: int
    ):
        linked_folder = os.path.join(
            parent_folder, f"linked_{message.chat_id}_{message.id}"
        )
        os.makedirs(linked_folder, exist_ok=True)

        await self._save_text(message, linked_folder)
        if message.media:
            await self._save_media(message, linked_folder)

        # We could recurse further but limit it
        if depth < 2:
            # Look for links in THIS linked message too? Maybe not needed for now to avoid bloat
            pass

    async def _save_text(self, message: Message, folder: str):
        data = {
            "id": message.id,
            "chat_id": message.chat_id,
            "date": message.date.isoformat() if message.date else None,
            "text": message.text,
            "grouped_id": message.grouped_id,
            "forward": self._get_forward_info(message),
            "reply_to": message.reply_to_msg_id
            if hasattr(message, "reply_to_msg_id")
            else None,
        }

        path = os.path.join(folder, "meta.json")
        tmp_path = path + ".tmp"
        try:
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        if message.text:
            txt_path = os.path.join(folder, "message.txt")
            tmp_txt_path = txt_path + ".tmp"
            try:
                async with aiofiles.open(tmp_txt_path, "w", encoding="utf-8") as f:
                    await f.write(message.text)
                os.replace(tmp_txt_path, txt_path)
            except Exception:
                if os.path.exists(tmp_txt_path):
                    os.remove(tmp_txt_path)
                raise

    def _get_forward_info(self, message: Message):
        if message.fwd_from:
            fwd = message.fwd_from
            from_id = None
            if fwd.from_id:
                if hasattr(fwd.from_id, "user_id"):
                    from_id = fwd.from_id.user_id
                elif hasattr(fwd.from_id, "channel_id"):
                    from_id = fwd.from_id.channel_id
                elif hasattr(fwd.from_id, "chat_id"):
                    from_id = fwd.from_id.chat_id

            return {
                "date": fwd.date.isoformat() if fwd.date else None,
                "from_id": from_id,
                "from_name": fwd.from_name,
                "post_author": fwd.post_author,
            }
        return None

    async def _save_media(self, message: Message, folder: str):
        # 1. Skip if we already have a valid non-zero file in this folder
        # (excluding meta.json, message.txt, and directories like telegraph_*)
        for f in os.listdir(folder):
            full_path = os.path.join(folder, f)
            if (
                f in ["meta.json", "message.txt"]
                or f.startswith(".")
                or os.path.isdir(full_path)
            ):
                continue
            if os.path.getsize(full_path) > 0:
                return

        try:
            # We want to download the main media or the webpage preview content
            media = message.media
            if not media:
                return

            # For WebPage media, download its document or photo
            if isinstance(media, MessageMediaWebPage) and media.webpage:
                if isinstance(media.webpage, WebPage):
                    media = media.webpage.document or media.webpage.photo
                else:
                    return  # e.g. WebPageEmpty

            if not media:
                return

            with tqdm(
                total=0,
                unit="B",
                unit_scale=True,
                desc=f"Media {message.id}",
                leave=False,
            ) as pbar:

                def callback(current, total):
                    if total:
                        pbar.total = total
                    pbar.n = current
                    pbar.refresh()

                # Create a temporary directory in the same folder for downloading
                # This ensures Telethon chooses the original filename inside it
                tmp_dir = os.path.join(folder, f".tmp_{uuid.uuid4().hex[:8]}")
                os.makedirs(tmp_dir, exist_ok=True)

                try:
                    # Telethon will use tmp_dir and choose the filename automatically
                    downloaded_path = await self.client.download_media(
                        media, file=tmp_dir, progress_callback=callback
                    )

                    if downloaded_path and os.path.exists(downloaded_path):
                        if os.path.getsize(downloaded_path) > 0:
                            final_filename = os.path.basename(downloaded_path)
                            final_path = os.path.join(folder, final_filename)
                            # Atomically move the file to the final location
                            os.replace(downloaded_path, final_path)
                finally:
                    # Clean up the temporary directory and any partial files
                    if os.path.exists(tmp_dir):
                        shutil.rmtree(tmp_dir, ignore_errors=True)
        except (Exception, asyncio.CancelledError) as e:
            # We catch CancelledError specifically if we want, but it's often a subclass of BaseException
            # In most cases Exception is enough, but for CLI we might want to catch more.
            # Telethon might raise its own errors.
            print(f"Failed to download media for msg {message.id}: {e}")
            if isinstance(e, asyncio.CancelledError):
                raise

    async def _download_telegraph(self, folder: str, url: str):
        # 0. Skip if already exists
        if os.path.exists(os.path.join(folder, "index.html")):
            if os.path.getsize(os.path.join(folder, "index.html")) > 0:
                return

        os.makedirs(folder, exist_ok=True)
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    print(f"Failed to fetch telegraph {url}: HTTP {response.status}")
                    return

                content_type = response.headers.get("Content-Type", "").lower()

                # Handle direct image/file links (e.g., telegra.ph/file/...)
                if "text/html" not in content_type:
                    ext = os.path.splitext(url.split("?")[0])[1]
                    if not ext:
                        if "image/" in content_type:
                            ext = "." + content_type.split("/")[1]

                    filename = f"direct_file{ext}"
                    final_path = os.path.join(folder, filename)
                    tmp_path = final_path + ".tmp"
                    try:
                        async with aiofiles.open(tmp_path, "wb") as f:
                            await f.write(await response.read())
                        os.replace(tmp_path, final_path)
                    except Exception:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        raise
                    return

                html = await response.text()
        except Exception as e:
            print(f"Failed to fetch telegraph {url}: {type(e).__name__}: {e}")
            return

        soup = bs(html, "html.parser")

        # 1. If JS is disabled, remove all script tags and don't download them
        if not self.download_js:
            for script in soup.find_all("script"):
                script.decompose()

        # 2. Collect all assets to download (tag, attribute, local_dir)
        asset_targets = [
            ("img", "src", "images"),
            ("video", "src", "images"),
            ("video", "poster", "images"),
            ("audio", "src", "images"),
            ("source", "src", "images"),
            ("link", "href", "css"),
        ]
        if self.download_js:
            asset_targets.append(("script", "src", "js"))

        asset_tasks = []
        for tag, attr, local_dir in asset_targets:
            for el in soup.find_all(tag):
                val = el.get(attr)
                if not val:
                    continue

                # Filter links: we only want stylesheets and icons
                if tag == "link":
                    rel = el.get("rel", [])
                    if isinstance(rel, str):
                        rel = [rel]
                    if "stylesheet" in rel:
                        local_dir = "css"
                    elif any(
                        r in rel for r in ["icon", "shortcut icon", "apple-touch-icon"]
                    ):
                        local_dir = "images"
                    else:
                        continue  # Skip other links (canonical, alternate, etc.)

                asset_tasks.append((el, attr, val, local_dir))

        # 2. Download and update paths
        if asset_tasks:
            pbar = tqdm(
                total=len(asset_tasks),
                desc="Telegraph Assets",
                unit="file",
                leave=False,
            )
            for i, (el, attr, orig_val, local_dir) in enumerate(asset_tasks):
                src = orig_val

                # Normalize URL
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://telegra.ph" + src
                elif src.startswith("tps://"):
                    src = "https://" + src[6:]
                elif not src.startswith("http"):
                    src = "https://" + src

                # Generate local path
                # Skip external trackers/analytics if possible, but keep it simple for now
                if "google-analytics.com" in src:
                    pbar.update(1)
                    continue

                filename = os.path.basename(src.split("?")[0])
                if not filename or filename.endswith("/"):
                    filename = f"asset_{i}"

                # Ensure unique filename to avoid collisions in same local_dir
                filename = f"{i}_{filename}"

                local_subdir = os.path.join(folder, local_dir)
                os.makedirs(local_subdir, exist_ok=True)

                final_path = os.path.join(local_subdir, filename)
                tmp_path = final_path + ".tmp"
                local_rel_path = f"{local_dir}/{filename}"

                # Download if not already present
                if not (os.path.exists(final_path) and os.path.getsize(final_path) > 0):
                    try:
                        async with self.session.get(src) as r:
                            if r.status == 200:
                                content = await r.read()
                                if content:
                                    async with aiofiles.open(tmp_path, "wb") as f:
                                        await f.write(content)
                                    os.replace(tmp_path, final_path)
                            else:
                                # print(f"\n  Failed to download asset {src}: HTTP {r.status}")
                                pass
                    except Exception:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        pass

                # Update path in HTML only if final file exists
                if os.path.exists(final_path):
                    el[attr] = local_rel_path

                pbar.update(1)
            pbar.close()

        # 3. Save modified HTML atomically
        final_html_path = os.path.join(folder, "index.html")
        tmp_html_path = final_html_path + ".tmp"
        try:
            async with aiofiles.open(tmp_html_path, "w", encoding="utf-8") as f:
                await f.write(soup.prettify())
            os.replace(tmp_html_path, final_html_path)
        except Exception:
            if os.path.exists(tmp_html_path):
                os.remove(tmp_html_path)
            raise

        return
