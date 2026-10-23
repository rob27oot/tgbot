# bot/services/downloader.py
# غلاف yt-dlp لتنزيل الفيديوهات بدون تعطيل البوت (يشتغل بـ thread منفصل)
# + خطة بديلة لتويتر عبر fxtwitter (للتغريدات الحساسة اللي yt-dlp ما يشوفها)

import asyncio
import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yt_dlp

from bot.config import settings
from bot.utils.validators import detect_platform

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # اعادة المحاولة مرتين عند مشاكل الشبكة
_semaphore = asyncio.Semaphore(3)  # اقصى 3 تنزيلات متزامنة بالبوت كله
HAS_FFMPEG = shutil.which("ffmpeg") is not None
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}

_TWEET_RE = re.compile(r"^/([^/]+)/status/(\d+)")
_FX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class DownloaderError(Exception):
    """خطأ برسالة جاهزة للمستخدم."""

    def __init__(self, user_message: str, retryable: bool = False) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


@dataclass
class DownloadResult:
    path: Path
    workdir: Path
    title: str
    duration: int | None
    size_bytes: int
    quality: str | None
    width: int | None
    height: int | None


def cleanup(workdir: Path) -> None:
    """حذف المجلد المؤقت."""
    shutil.rmtree(workdir, ignore_errors=True)


def _too_large_error() -> DownloaderError:
    return DownloaderError(
        f"📦 حجم الفيديو أكبر من الحد المسموح ({settings.max_file_size_mb} ميغابايت)."
    )


def _classify_error(exc: Exception) -> DownloaderError:
    """تحويل أخطاء yt-dlp الى رسائل عربية واضحة."""
    text = str(exc).lower()
    if any(k in text for k in ("private", "log in", "login", "sign in", "protected", "authenticat")):
        return DownloaderError("🔒 هذا الفيديو خاص أو يحتاج تسجيل دخول.")
    if any(k in text for k in ("geo", "country", "region")):
        return DownloaderError("🌍 هذا الفيديو محظور في منطقتنا.")
    if any(
        k in text
        for k in ("timed out", "timeout", "connection", "network", "temporary failure",
                  "unable to download webpage", "http error 5", "remote end closed", "reset by peer")
    ):
        return DownloaderError("⚠️ مشكلة بالاتصال، حاول مرة ثانية.", retryable=True)
    if any(
        k in text
        for k in ("not available", "unavailable", "removed", "deleted", "does not exist",
                  "no video", "not found", "404")
    ):
        return DownloaderError("❌ الفيديو محذوف أو غير متاح.")
    return DownloaderError("❌ ما گدرت أنزّل هذا الفيديو. تأكد من الرابط وحاول مرة ثانية.")


def _build_opts(workdir: Path) -> dict:
    # بدون ffmpeg ما نگدر ندمج صوت وصورة، فنختار ملف جاهز واحد
    if HAS_FFMPEG:
        fmt = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
    else:
        fmt = "b[ext=mp4]/b"
    return {
        "format": fmt,
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
        "socket_timeout": 20,
        "retries": 2,
    }


def _first_entry(info: dict | None) -> dict | None:
    if info and info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        return entries[0] if entries else None
    return info


def _estimate_size(info: dict) -> int | None:
    size = info.get("filesize") or info.get("filesize_approx")
    if size:
        return int(size)
    total = 0
    for fmt in info.get("requested_formats") or []:
        part = fmt.get("filesize") or fmt.get("filesize_approx")
        if not part:
            return None
        total += int(part)
    return total or None


def _find_file(info: dict, workdir: Path) -> Path | None:
    for item in info.get("requested_downloads") or []:
        filepath = item.get("filepath")
        if filepath and Path(filepath).exists():
            return Path(filepath)
    files = [p for p in workdir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    return max(files, key=lambda p: p.stat().st_size) if files else None


def _sync_download(url: str, workdir: Path) -> DownloadResult:
    """التنزيل الفعلي بـ yt-dlp (متزامن)، يشتغل داخل thread."""
    try:
        with yt_dlp.YoutubeDL(_build_opts(workdir)) as ydl:
            # المرحلة 1: جلب المعلومات والتحقق من الحجم قبل التنزيل
            info = _first_entry(ydl.extract_info(url, download=False))
            if not info:
                raise DownloaderError("❌ الفيديو محذوف أو غير متاح.")
            estimated = _estimate_size(info)
            if estimated and estimated > settings.max_file_size_bytes:
                raise _too_large_error()

            # المرحلة 2: التنزيل
            info = _first_entry(ydl.extract_info(url, download=True))
            if not info:
                raise DownloaderError("❌ ما گدرت أنزّل هذا الفيديو.")
    except DownloaderError:
        raise
    except yt_dlp.utils.YoutubeDLError as exc:
        logger.warning("yt-dlp error for %s: %s", url, exc)
        raise _classify_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected downloader error for %s", url)
        raise DownloaderError("❌ صار خطأ غير متوقع أثناء التنزيل.") from exc

    path = _find_file(info, workdir)
    if path is None:
        raise DownloaderError("❌ ما گدرت أنزّل هذا الفيديو.")

    size = path.stat().st_size
    if size > settings.max_file_size_bytes:
        raise _too_large_error()

    height = info.get("height")
    return DownloadResult(
        path=path,
        workdir=workdir,
        title=(info.get("title") or "فيديو")[:200],
        duration=int(info["duration"]) if info.get("duration") else None,
        size_bytes=size,
        quality=f"{height}p" if height else None,
        width=info.get("width"),
        height=height,
    )


async def _fx_twitter_download(url: str, workdir: Path) -> DownloadResult:
    """خطة بديلة لتويتر: نجيب رابط الفيديو من fxtwitter وننزله بـ httpx."""
    match = _TWEET_RE.match(urlparse(url).path)
    if not match:
        raise DownloaderError("❌ الرابط غير صالح.")
    user, tweet_id = match.groups()

    try:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=_FX_HEADERS
        ) as client:
            resp = await client.get(f"https://api.fxtwitter.com/{user}/status/{tweet_id}")
            if resp.status_code != 200:
                raise DownloaderError("❌ الفيديو محذوف أو غير متاح.")

            tweet = resp.json().get("tweet") or {}
            media = tweet.get("media") or {}
            videos = media.get("videos") or [
                m for m in (media.get("all") or []) if m.get("type") in ("video", "gif")
            ]
            if not videos or not videos[0].get("url"):
                raise DownloaderError("❌ هذي التغريدة ما بيها فيديو.")
            video = videos[0]

            path = workdir / f"{tweet_id}.mp4"
            size = 0
            async with client.stream("GET", video["url"]) as stream:
                if stream.status_code != 200:
                    raise DownloaderError("❌ ما گدرت أنزّل هذا الفيديو.")
                length = stream.headers.get("content-length")
                if length and int(length) > settings.max_file_size_bytes:
                    raise _too_large_error()
                with open(path, "wb") as file:
                    async for chunk in stream.aiter_bytes(65536):
                        size += len(chunk)
                        if size > settings.max_file_size_bytes:
                            raise _too_large_error()
                        file.write(chunk)
    except DownloaderError:
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("fxtwitter fallback failed for %s: %s", url, exc)
        raise DownloaderError("⚠️ مشكلة بالاتصال، حاول مرة ثانية.") from exc

    height = video.get("height")
    duration = video.get("duration")
    return DownloadResult(
        path=path,
        workdir=workdir,
        title=(tweet.get("text") or "فيديو")[:200],
        duration=int(duration) if duration else None,
        size_bytes=size,
        quality=f"{height}p" if height else None,
        width=video.get("width"),
        height=height,
    )


async def _ytdlp_with_retries(url: str, workdir: Path) -> DownloadResult:
    """yt-dlp مع اعادة المحاولة مرتين عند مشاكل الشبكة."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await asyncio.to_thread(_sync_download, url, workdir)
        except DownloaderError as err:
            if err.retryable and attempt < MAX_RETRIES:
                logger.info("Retry %d for %s", attempt + 1, url)
                await asyncio.sleep(2 * (attempt + 1))
                continue
            raise
    raise DownloaderError("❌ ما گدرت أنزّل هذا الفيديو.")


async def download_video(url: str) -> DownloadResult:
    """
    تنزيل فيديو من الرابط. يرمي DownloaderError برسالة عربية عند الفشل.
    مهم: المستدعي مسؤول عن استدعاء cleanup(result.workdir) بعد الارسال.
    """
    workdir = settings.download_dir / uuid.uuid4().hex
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        async with _semaphore:
            try:
                return await _ytdlp_with_retries(url, workdir)
            except DownloaderError as err:
                # الخطة البديلة لتويتر فقط، وما نجربها اذا السبب حجم الفيديو (📦)
                if detect_platform(url) != "twitter" or "📦" in err.user_message:
                    raise
                logger.info("yt-dlp failed for %s, trying fxtwitter fallback", url)
                return await _fx_twitter_download(url, workdir)
    except BaseException:
        cleanup(workdir)
        raise