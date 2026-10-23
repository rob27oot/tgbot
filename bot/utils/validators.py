# bot/utils/validators.py
# التحقق من الروابط (تيك توك / تويتر) + دوال مساعدة للتنسيق

import re
from urllib.parse import urlparse

MAX_URL_LENGTH = 300

# يقبل فقط حروف الروابط الاعتيادية (بدون حروف عربية ملتصقة بالرابط)
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")

TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
TIKTOK_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
TWITTER_HOSTS = {
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
    "x.com", "www.x.com", "mobile.x.com",
}

_TIKTOK_PATH_RE = re.compile(r"^/(?:@[\w.\-]+/video/\d+|t/[\w\-]+)/?$")
_TIKTOK_SHORT_PATH_RE = re.compile(r"^/[\w\-]+/?$")
_TWITTER_PATH_RE = re.compile(r"^/(?:[A-Za-z0-9_]{1,15}|i/web|i)/status/\d+(?:/.*)?$")

_TRAILING = ".,;:!?)]}>'\"،؟"


def extract_url(text: str) -> str | None:
    """استخراج أول رابط من نص الرسالة."""
    match = _URL_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(_TRAILING)


def normalize_url(url: str) -> str:
    """حذف باراميترات التتبع (كل شي بعد ؟ و #)."""
    return url.split("?", 1)[0].split("#", 1)[0]


def detect_platform(url: str) -> str | None:
    """
    يرجع 'tiktok' او 'twitter' اذا الرابط صالح، وإلا None.
    يرفض الروابط المشبوهة (يوزر داخل الرابط، منفذ غريب، دومين مزيف).
    """
    if not url or len(url) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.username or parsed.password:  # مثل https://tiktok.com@evil.com
        return None
    if port not in (None, 80, 443):
        return None

    path = parsed.path
    if host in TIKTOK_HOSTS and _TIKTOK_PATH_RE.match(path):
        return "tiktok"
    if host in TIKTOK_SHORT_HOSTS and _TIKTOK_SHORT_PATH_RE.match(path):
        return "tiktok"
    if host in TWITTER_HOSTS and _TWITTER_PATH_RE.match(path):
        return "twitter"
    return None


def parse_link(text: str) -> tuple[str, str] | None:
    """من نص الرسالة يرجع (المنصة, الرابط النظيف) او None."""
    url = extract_url(text)
    if not url:
        return None
    url = normalize_url(url)
    platform = detect_platform(url)
    if not platform:
        return None
    return platform, url


def format_size(size_bytes: int | None) -> str:
    """تحويل الحجم الى نص مقروء."""
    if not size_bytes:
        return "غير معروف"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def format_duration(seconds: int | None) -> str:
    """تحويل الثواني الى mm:ss او h:mm:ss."""
    if not seconds:
        return "غير معروف"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


PLATFORM_NAMES = {"tiktok": "تيك توك", "twitter": "تويتر (X)"}