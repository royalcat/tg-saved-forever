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
        with open(self.state_file, "w") as f:
            json.dump({"last_msg_id": self.last_msg_id}, f)

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

        messages = []
        async for message in self.client.iter_messages(
            "me", min_id=self.last_msg_id, limit=limit, reverse=True
        ):
            messages.append(message)

        if not messages:
            print("No new messages to backup.")
            return

        pbar = tqdm(total=len(messages), desc="Backing up messages", unit="msg")
        for message in messages:
            try:
                await self._process_message(message)
                if message.id > self.last_msg_id:
                    self.last_msg_id = message.id
                    self._save_state()
            except Exception as e:
                print(f"Error processing message {message.id}: {e}")
            pbar.update(1)
        pbar.close()

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
                    telegraph_urls.add(url)

        # Also check message.media.webpage
        if isinstance(message.media, MessageMediaWebPage) and isinstance(
            message.media.webpage, WebPage
        ):
            if message.media.webpage.url and "telegra.ph" in message.media.webpage.url:
                telegraph_urls.add(message.media.webpage.url)

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
            "forward": self._get_forward_info(message),
            "reply_to": message.reply_to_msg_id
            if hasattr(message, "reply_to_msg_id")
            else None,
        }

        path = os.path.join(folder, "meta.json")
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

        if message.text:
            txt_path = os.path.join(folder, "message.txt")
            async with aiofiles.open(txt_path, "w", encoding="utf-8") as f:
                await f.write(message.text)

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
        # Find if media already exists (basic check)
        # Telethon downloads with original filename if possible

        try:
            # We don't know the filename before download easily without more complex logic
            # Let's just download. client.download_media will handle path.

            with tqdm(
                total=0, unit="B", unit_scale=True, desc="Media", leave=False
            ) as pbar:

                def callback(current, total):
                    pbar.total = total
                    pbar.n = current
                    pbar.refresh()

                # download_media returns the path where it was saved
                await self.client.download_media(
                    message, file=folder, progress_callback=callback
                )
        except Exception as e:
            print(f"Failed to download media for msg {message.id}: {e}")

    async def _download_telegraph(self, folder: str, url: str):
        os.makedirs(folder, exist_ok=True)
        try:
            async with self.session.get(url) as page:
                if page.status != 200:
                    return
                html = await page.text()
        except Exception as e:
            print(f"Failed to fetch telegraph {url}: {e}")
            return

        # Save HTML
        async with aiofiles.open(
            os.path.join(folder, "index.html"), "w", encoding="utf-8"
        ) as f:
            await f.write(html)

        soup = bs(html, "html.parser")
        images = soup.findAll("img")

        if images:
            img_folder = os.path.join(folder, "images")
            os.makedirs(img_folder, exist_ok=True)

            for i, img in enumerate(images):
                src = img.get("src")
                if not src:
                    continue
                if src.startswith("/"):
                    src = "https://telegra.ph" + src

                img_name = f"{i}_{os.path.basename(src)}"
                img_path = os.path.join(img_folder, img_name)

                try:
                    async with self.session.get(src) as r:
                        if r.status == 200:
                            async with aiofiles.open(img_path, "wb") as f:
                                await f.write(await r.read())
                except Exception:
                    pass
