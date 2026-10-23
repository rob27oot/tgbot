# tests/try_download.py
# اختبار يدوي للتنزيل: python -m tests.try_download "الرابط"

import asyncio
import sys

from bot.services.downloader import DownloaderError, cleanup, download_video
from bot.utils.validators import parse_link


async def main(text: str) -> None:
    parsed = parse_link(text)
    if not parsed:
        print("INVALID LINK")
        return
    platform, url = parsed
    print("platform:", platform, "| url:", url)
    try:
        r = await download_video(url)
    except DownloaderError as e:
        print("DownloaderError:", e.user_message)
        return
    print("title   :", r.title)
    print("duration:", r.duration)
    print("size    :", r.size_bytes)
    print("quality :", r.quality)
    print("path    :", r.path)
    cleanup(r.workdir)
    print("OK")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m tests.try_download "URL"')
    else:
        asyncio.run(main(sys.argv[1]))