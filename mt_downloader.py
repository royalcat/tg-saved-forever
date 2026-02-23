from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, cast, runtime_checkable

import aiofiles
import aiohttp
from bs4 import BeautifulSoup as bs
from bs4 import Tag
from telethon import TelegramClient
from telethon.tl.types import (
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageFwdHeader,
    MessageMediaWebPage,
    PeerChannel,
    PeerUser,
    User,
    WebPage,
)
from tqdm.asyncio import tqdm

# Type alias for raw JSON dicts
type JsonDict = dict[str, object]

mobile_device = {
    "device_model": "Pixel 6",
    "system_version": "15",
    "app_version": "12.4.0",
    "lang_code": "en",
    "system_lang_code": "en-US",
}


@runtime_checkable
class TelegramMessage(Protocol):
    """Protocol describing the Telethon Message interface we use."""

    @property
    def id(self) -> int: ...
    @property
    def text(self) -> str | None: ...
    @property
    def date(self) -> datetime | None: ...
    @property
    def chat_id(self) -> int: ...
    @property
    def media(self) -> object | None: ...
    @property
    def entities(self) -> Sequence[object] | None: ...
    @property
    def fwd_from(self) -> MessageFwdHeader | None: ...
    @property
    def grouped_id(self) -> int | None: ...
    @property
    def reply_to_msg_id(self) -> int | None: ...


class MTDownloader:
    client: TelegramClient
    session: aiohttp.ClientSession
    base_path: str
    download_js: bool
    state_file: str
    last_msg_id: int

    def __init__(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        base_path: str = "./downloads",
        download_js: bool = False,
    ) -> None:
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
        self.session = aiohttp.ClientSession()
        self.base_path = base_path
        self.download_js = download_js
        self.state_file = os.path.join(self.base_path, ".state.json")
        os.makedirs(self.base_path, exist_ok=True)
        self.last_msg_id = self._load_state()

    def _load_state(self) -> int:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    raw = cast(object, json.load(f))
                    if isinstance(raw, dict):
                        d = cast(JsonDict, raw)
                        val = d.get("last_msg_id", 0)
                        if isinstance(val, int):
                            return val
            except Exception:
                pass
        return 0

    def _save_state(self) -> None:
        tmp_state_file = self.state_file + ".tmp"
        try:
            with open(tmp_state_file, "w") as f:
                json.dump({"last_msg_id": self.last_msg_id}, f)
            os.replace(tmp_state_file, self.state_file)
        except Exception:
            if os.path.exists(tmp_state_file):
                os.remove(tmp_state_file)
            raise

    async def start(self, phone: str | None = None) -> None:
        print("Attempting to connect to Telegram...")
        if phone is not None:
            await self.client.start(phone=phone)  # pyright: ignore[reportGeneralTypeIssues]
        else:
            await self.client.start()  # pyright: ignore[reportGeneralTypeIssues]

    async def close(self) -> None:
        self.client.disconnect()  # pyright: ignore[reportUnusedCallResult]
        if self.session:
            await self.session.close()

    async def backup_saved_messages(self, limit: int | None = None) -> None:
        """Backups messages from 'Saved Messages'."""
        me = await self.client.get_me()
        if isinstance(me, User):
            display_name: str = me.username or me.first_name or "Unknown"
            print(f"Connected as {display_name}")
        else:
            print("Connected.")

        print(f"Checking for messages newer than ID: {self.last_msg_id}")

        # Create the iterator with explicit kwargs
        if limit is not None:
            it = self.client.iter_messages(
                "me", min_id=self.last_msg_id, limit=limit, reverse=True
            )
        else:
            it = self.client.iter_messages("me", min_id=self.last_msg_id, reverse=True)

        pbar = tqdm(desc="Backing up", unit="msg", dynamic_ncols=True)

        # Iterate and process immediately to prevent file reference expiration
        async for message in it:  # pyright: ignore[reportUnknownVariableType]
            pbar.total = it.total
            # Update progress bar description with dynamic message info
            msg = cast(TelegramMessage, message)
            msg_date_str: str = msg.date.strftime("%Y-%m-%d") if msg.date else "Unknown"
            pbar.set_description(f"Msg {msg.id} ({msg_date_str})")

            # Process the message immediately
            await self._process_message(msg)

            if msg.id > self.last_msg_id:
                self.last_msg_id = msg.id
                self._save_state()

            _ = pbar.update(1)

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
        url = url.rstrip("/")

        # 3. Strip redundant tracking parameters if any (basic check)
        if "?" in url:
            base, _query = url.split("?", 1)
            url = base

        return url

    async def _process_message(self, message: TelegramMessage, depth: int = 0) -> None:
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
        telegraph_urls: set[str] = set()
        if message.entities:
            for entity in message.entities:
                url: str | None = None
                if isinstance(entity, MessageEntityTextUrl):
                    url = entity.url
                elif isinstance(entity, MessageEntityUrl):
                    # For plain URLs, we need to extract from text
                    msg_text = message.text
                    if msg_text is not None:
                        url = msg_text[entity.offset : entity.offset + entity.length]

                if url and "telegra.ph" in url:
                    telegraph_urls.add(self._normalize_url(url))

        # Also check message.media.webpage
        if isinstance(message.media, MessageMediaWebPage) and isinstance(
            message.media.webpage, WebPage
        ):
            wp_url: str | None = message.media.webpage.url
            if wp_url and "telegra.ph" in wp_url:
                telegraph_urls.add(self._normalize_url(wp_url))

        for i, url in enumerate(telegraph_urls):
            await self._download_telegraph(
                os.path.join(msg_folder, f"telegraph_{i}"), url
            )

        # 4. Process Message Links (t.me/...)
        await self._process_links(message, depth)

    async def _process_links(self, message: TelegramMessage, depth: int) -> None:
        msg_text = message.text
        if not msg_text:
            return

        # Improved regex for telegram message links
        link_pattern = re.compile(
            r"(?:https?://)?t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)"
        )
        matches: list[tuple[str, ...]] = link_pattern.findall(msg_text)

        for match in matches:
            channel_id_str, username, msg_id_str = match
            msg_id = int(msg_id_str)

            peer: str | int | None = None
            if channel_id_str:
                try:
                    # Private channels in Telethon need to be prefixed with -100 if only digits
                    peer = int(f"-100{channel_id_str}")
                except ValueError:
                    continue
            else:
                peer = username

            try:
                fetched = await self.client.get_messages(peer, ids=[msg_id])  # pyright: ignore[reportUnknownMemberType]
                fetched_list: list[object] = (
                    list(fetched) if isinstance(fetched, list) else [fetched]
                )
                if fetched_list and fetched_list[0]:
                    fetched_msg = cast(TelegramMessage, fetched_list[0])
                    parent_folder = os.path.join(self.base_path, str(message.id))
                    await self._process_linked_message(
                        fetched_msg, parent_folder, depth + 1
                    )
            except Exception:
                # Failed to fetch linked message
                pass

    async def _process_linked_message(
        self, message: TelegramMessage, parent_folder: str, depth: int
    ) -> None:
        linked_folder = os.path.join(
            parent_folder, f"linked_{message.chat_id}_{message.id}"
        )
        os.makedirs(linked_folder, exist_ok=True)

        await self._save_text(message, linked_folder)
        if message.media:
            await self._save_media(message, linked_folder)

        # We could recurse further but limit it
        if depth < 2:
            pass

    async def _save_text(self, message: TelegramMessage, folder: str) -> None:
        data: dict[str, object] = {
            "id": message.id,
            "chat_id": message.chat_id,
            "date": message.date.isoformat() if message.date else None,
            "text": message.text,
            "grouped_id": message.grouped_id,
            "forward": self._get_forward_info(message),
            "reply_to": message.reply_to_msg_id,
        }

        path = os.path.join(folder, "meta.json")
        tmp_path = path + ".tmp"
        try:
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                _ = await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        msg_text = message.text
        if msg_text:
            txt_path = os.path.join(folder, "message.txt")
            tmp_txt_path = txt_path + ".tmp"
            try:
                async with aiofiles.open(tmp_txt_path, "w", encoding="utf-8") as f:
                    _ = await f.write(msg_text)
                os.replace(tmp_txt_path, txt_path)
            except Exception:
                if os.path.exists(tmp_txt_path):
                    os.remove(tmp_txt_path)
                raise

    def _get_forward_info(self, message: TelegramMessage) -> dict[str, object] | None:
        fwd = message.fwd_from
        if fwd is not None:
            from_id: int | None = None
            peer = fwd.from_id
            if peer is not None:
                if isinstance(peer, PeerUser):
                    from_id = peer.user_id
                elif isinstance(peer, PeerChannel):
                    from_id = peer.channel_id
                else:
                    from_id = peer.chat_id

            return {
                "date": fwd.date.isoformat() if fwd.date else None,
                "from_id": from_id,
                "from_name": fwd.from_name,
                "post_author": fwd.post_author,
            }
        return None

    async def _save_media(self, message: TelegramMessage, folder: str) -> None:
        # 1. Skip if we already have a valid non-zero file in this folder
        for f_name in os.listdir(folder):
            full_path = os.path.join(folder, f_name)
            if (
                f_name in ("meta.json", "message.txt")
                or f_name.startswith(".")
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

                def callback(current: int, total: int) -> None:
                    if total:
                        pbar.total = total
                    pbar.n = current
                    pbar.refresh()

                # Create a temporary directory in the same folder for downloading
                tmp_dir = os.path.join(folder, f".tmp_{uuid.uuid4().hex[:8]}")
                os.makedirs(tmp_dir, exist_ok=True)

                try:
                    # Telethon will use tmp_dir and choose the filename automatically
                    downloaded_path = await self.client.download_media(
                        media,  # pyright: ignore[reportArgumentType]
                        file=tmp_dir,
                        progress_callback=callback,
                    )

                    if (
                        downloaded_path
                        and isinstance(downloaded_path, str)
                        and os.path.exists(downloaded_path)
                    ):
                        if os.path.getsize(downloaded_path) > 0:
                            final_filename = os.path.basename(downloaded_path)
                            final_path = os.path.join(folder, final_filename)
                            os.replace(downloaded_path, final_path)
                finally:
                    if os.path.exists(tmp_dir):
                        shutil.rmtree(tmp_dir, ignore_errors=True)
        except (Exception, asyncio.CancelledError) as e:
            print(f"Failed to download media for msg {message.id}: {e}")
            if isinstance(e, asyncio.CancelledError):
                raise

    async def _download_telegraph(self, folder: str, url: str) -> None:
        # 0. Skip if already exists
        index_path = os.path.join(folder, "index.html")
        if os.path.exists(index_path) and os.path.getsize(index_path) > 0:
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
                            _ = await f.write(await response.read())
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
        asset_targets: list[tuple[str, str, str]] = [
            ("img", "src", "images"),
            ("video", "src", "images"),
            ("video", "poster", "images"),
            ("audio", "src", "images"),
            ("source", "src", "images"),
            ("link", "href", "css"),
        ]
        if self.download_js:
            asset_targets.append(("script", "src", "js"))

        asset_tasks: list[tuple[Tag, str, str, str]] = []
        for tag_name, attr, local_dir in asset_targets:
            for el in soup.find_all(tag_name):
                val = el.get(attr)
                if not val or not isinstance(val, str):
                    continue

                target_dir = local_dir

                # Filter links: we only want stylesheets and icons
                if tag_name == "link":
                    rel = el.get("rel")
                    if rel is None:
                        continue
                    # BS4 returns rel as a list of strings
                    rel_list: list[str]
                    if isinstance(rel, list):
                        rel_list = [str(r) for r in rel]
                    else:
                        rel_list = [str(rel)]

                    if "stylesheet" in rel_list:
                        target_dir = "css"
                    elif any(
                        r in rel_list
                        for r in ("icon", "shortcut icon", "apple-touch-icon")
                    ):
                        target_dir = "images"
                    else:
                        continue  # Skip other links (canonical, alternate, etc.)

                asset_tasks.append((el, attr, val, target_dir))

        # 2. Download and update paths
        if asset_tasks:
            asset_pbar = tqdm(
                total=len(asset_tasks),
                desc="Telegraph Assets",
                unit="file",
                leave=False,
                dynamic_ncols=True,
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

                # Skip external trackers/analytics
                if "google-analytics.com" in src:
                    _ = asset_pbar.update(1)
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
                                        _ = await f.write(content)
                                    os.replace(tmp_path, final_path)
                    except Exception:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)

                # Update path in HTML only if final file exists
                if os.path.exists(final_path):
                    el[attr] = local_rel_path

                _ = asset_pbar.update(1)
            asset_pbar.close()

        # 3. Save modified HTML atomically
        final_html_path = os.path.join(folder, "index.html")
        tmp_html_path = final_html_path + ".tmp"
        try:
            async with aiofiles.open(tmp_html_path, "w", encoding="utf-8") as f:
                _ = await f.write(soup.prettify())
            os.replace(tmp_html_path, final_html_path)
        except Exception:
            if os.path.exists(tmp_html_path):
                os.remove(tmp_html_path)
            raise
