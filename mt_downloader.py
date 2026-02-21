import asyncio
import io
import json
import os
import re
from typing import Optional

import aiofiles
import aiohttp
from bs4 import BeautifulSoup as bs
from telethon import TelegramClient
from telethon.tl.types import (
    Message,
    MessageEntityTextUrl,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
    WebPage,
)
from tqdm.asyncio import tqdm


class MTDownloader:
    def __init__(
        self,
        session_name: str,
        api_id: int,
        api_hash: str,
        base_path: str = "./downloads",
    ):
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.session = aiohttp.ClientSession()
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)

    async def start(self, phone: Optional[str] = None):
        print("Attempting to connect to Telegram...")
        print(
            "Note: If you are asked for a code, check your TELEGRAM APP on your phone or desktop first. Telegram often sends the code there instead of SMS."
        )

        await self.client.start(phone=phone)
        await self.client.connect()

    async def close(self):
        await self.client.disconnect()
        await self.session.close()

    async def backup_saved_messages(self, limit: Optional[int] = None):
        """Backups messages from 'Saved Messages'."""
        me = await self.client.get_me()
        print(f"Connected as {me.username or me.first_name}")

        pbar = tqdm(desc="Processing messages", unit="msg")
        async for message in self.client.iter_messages("me", limit=limit):
            await self._process_message(message)
            pbar.update(1)
        pbar.close()

    async def _process_message(self, message: Message, depth: int = 0):
        if depth > 1:  # Prevent infinite recursion
            return

        msg_id = message.id
        prefix = f"{message.id}" if depth == 0 else f"linked_{message.id}"

        # 1. Save Text
        if message.text:
            await self._save_text(message, prefix)

        # 2. Save Media
        if message.media:
            await self._save_media(message, prefix)

        # 3. Check for Telegraph links in text/entities
        if message.entities:
            for entity in message.entities:
                if (
                    isinstance(entity, MessageEntityTextUrl)
                    and "telegra.ph" in entity.url
                ):
                    await self._download_telegraph(f"{prefix}_telegraph", entity.url)

        # 4. Handle WebPage media (often telegraph)
        if isinstance(message.media, MessageMediaWebPage) and isinstance(
            message.media.webpage, WebPage
        ):
            if "telegra.ph" in message.media.webpage.url:
                await self._download_telegraph(
                    f"{prefix}_telegraph", message.media.webpage.url
                )

        # 5. Process Message Links
        await self._process_links(message, depth)

    async def _process_links(self, message: Message, depth: int):
        if not message.text:
            return

        # Regex to find telegram message links
        # Patterns: t.me/c/CHANNEL_ID/MSG_ID or t.me/USERNAME/MSG_ID
        link_pattern = re.compile(
            r"(?:https?://)?t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)"
        )
        matches = link_pattern.findall(message.text)

        for match in matches:
            channel_id_str, username, msg_id_str = match
            msg_id = int(msg_id_str)

            entity = None
            if channel_id_str:
                try:
                    entity = int(channel_id_str)
                except ValueError:
                    continue
            else:
                entity = username

            try:
                fetched_msgs = await self.client.get_messages(entity, ids=[msg_id])
                if fetched_msgs and fetched_msgs[0]:
                    await self._process_message(fetched_msgs[0], depth=depth + 1)

            except Exception as e:
                pass

    async def _save_text(self, message: Message, prefix: str = None):
        if prefix is None:
            prefix = str(message.id)

        data = {
            "id": message.id,
            "chat_id": message.chat_id,
            "date": message.date.isoformat(),
            "text": message.text,
            "forward": self._get_forward_info(message),
            "reply_to": message.reply_to_msg_id,
        }
        path = os.path.join(self.base_path, f"{prefix}_meta.json")
        if not os.path.exists(path):
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    def _get_forward_info(self, message: Message):
        if message.fwd_from:
            return {
                "date": message.fwd_from.date.isoformat()
                if message.fwd_from.date
                else None,
                "from_id": message.fwd_from.from_id.user_id
                if hasattr(message.fwd_from.from_id, "user_id")
                else None,
                "from_name": message.fwd_from.from_name,
            }
        return None

    async def _save_media(self, message: Message, prefix: str = None):
        if prefix is None:
            prefix = f"{message.id}"

        file_prefix = f"{prefix}_media"

        existing = [f for f in os.listdir(self.base_path) if f.startswith(file_prefix)]
        if existing:
            return

        try:
            # Determine size for progress bar if possible
            size = None
            if hasattr(message, "document") and message.document:
                size = message.document.size
            elif hasattr(message, "photo") and message.photo:
                # Photos have multiple sizes, Telethon downloads best by default
                pass

            with tqdm(
                total=size, unit="B", unit_scale=True, desc=file_prefix, leave=False
            ) as pbar:

                def callback(current, total):
                    pbar.total = total
                    pbar.n = current
                    pbar.refresh()

                path = await self.client.download_media(
                    message,
                    file=os.path.join(self.base_path, file_prefix),
                    progress_callback=callback,
                )
        except Exception as e:
            print(f"Failed to download media for {message.id}: {e}")

    async def _download_telegraph(self, name_prefix: str, url: str):
        try:
            async with self.session.get(url) as page:
                if page.content_type != "text/html":
                    return
                html = await page.text()
        except Exception as e:
            print(f"Failed to fetch telegraph {url}: {e}")
            return

        # Save HTML
        html_path = os.path.join(self.base_path, f"{name_prefix}.html")
        if not os.path.exists(html_path):
            async with aiofiles.open(html_path, "w", encoding="utf-8") as f:
                await f.write(html)

        # Parse and download images
        soup = bs(html, "html.parser")
        images = soup.findAll("img")

        for i, img in enumerate(images):
            src = img.get("src")
            if not src:
                continue

            if src.startswith("/"):
                src = "https://telegra.ph" + src

            img_name = f"{name_prefix}_img_{i}_{os.path.basename(src)}"
            img_path = os.path.join(self.base_path, img_name)

            if not os.path.exists(img_path):
                try:
                    async with self.session.get(src) as r:
                        if r.status == 200:
                            content = await r.read()
                            async with aiofiles.open(img_path, "wb") as f:
                                await f.write(content)
                except Exception as e:
                    print(f"Failed to download telegraph image {src}: {e}")
