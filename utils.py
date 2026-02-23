from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import cast

import aiofiles
import aiohttp
from bs4 import BeautifulSoup, Tag

IMAGE_FORMATS = ("png", "gif", "jpg", "bpm")


def flatten(
    container: list[object] | tuple[object, ...] | None,
) -> Generator[object, None, None]:
    if container is not None and len(container) > 0:
        for i in container:
            if isinstance(i, (list, tuple)):
                yield from flatten(cast("list[object] | tuple[object, ...]", i))
            else:
                yield i


def get_pages_for_tag(link: str) -> int:
    import requests

    text = requests.get(link).text

    soup = BeautifulSoup(text, features="html.parser")

    if soup.title is not None and soup.title.string == "No Images Found":
        return 0

    last_tag: Tag | None = None
    for a_tag in soup.find_all("a"):
        if a_tag.string == "Last":
            last_tag = a_tag
            break

    if last_tag is None:
        return 1  # When title is not "No Images Found" but there are no link, there are exactly one page

    href = last_tag.get("href")
    if not isinstance(href, str):
        return 1

    n_pages = int(href.split("/")[-1])
    return n_pages


async def get_elements_on_page(
    link: str,
    get_videos: bool,
    put_to: list[tuple[str, str]],
    semaphore: asyncio.Semaphore,
) -> None:
    _ = await semaphore.acquire()
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as resp:
            text = await resp.text()

    semaphore.release()

    soup = BeautifulSoup(text, features="html.parser")

    for parent_tag in soup.find_all("div", class_="shm-thumb thumb"):
        data_ext = parent_tag.get("data-ext")
        if (
            isinstance(data_ext, str)
            and data_ext not in IMAGE_FORMATS
            and not get_videos
        ):
            continue

        data_post_id = parent_tag.get("data-post-id")
        if not isinstance(data_post_id, str):
            continue
        object_name = data_post_id

        child_tag: Tag | None = None
        for a_tag in parent_tag.find_all("a"):
            if a_tag.string == "Image Only":
                child_tag = a_tag
                break
        if child_tag is None:
            continue

        child_link = child_tag.get("href")
        if not isinstance(child_link, str):
            continue

        put_to.append((child_link, object_name))


async def download_file(
    t: tuple[str, str],
    path: Path,
    semaphore: asyncio.Semaphore,
    vebrose: bool,
    skip_existing: bool,
) -> None:
    if skip_existing and (path / t[1]).exists():
        return

    _ = await semaphore.acquire()
    if vebrose:
        print(f"Downloading {t[0]}")
    async with aiohttp.ClientSession() as session:
        async with session.get(t[0]) as resp:
            if resp.status == 200:
                f = await aiofiles.open(path / t[1], mode="wb")
                _ = await f.write(await resp.read())
                await f.close()
    semaphore.release()
