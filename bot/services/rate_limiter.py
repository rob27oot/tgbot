# bot/services/rate_limiter.py
# تحديد عدد الطلبات بالدقيقة لكل مستخدم + منع تنزيلين بنفس الوقت

import time
from collections import defaultdict, deque


class RateLimiter:
    """نافذة زمنية متحركة: max_calls طلبات لكل period ثانية."""

    def __init__(self, max_calls: int = 3, period: int = 60) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: dict[int, deque[float]] = defaultdict(deque)

    def hit(self, user_id: int) -> int:
        """
        يسجل طلب جديد.
        يرجع 0 اذا مسموح، وإلا عدد الثواني المتبقية للانتظار.
        """
        now = time.monotonic()
        calls = self._calls[user_id]
        while calls and now - calls[0] >= self.period:
            calls.popleft()
        if len(calls) >= self.max_calls:
            return int(self.period - (now - calls[0])) + 1
        calls.append(now)
        return 0


class ActiveDownloads:
    """يمنع المستخدم من تشغيل أكثر من تنزيل بنفس الوقت."""

    def __init__(self) -> None:
        self._active: set[int] = set()

    def try_start(self, user_id: int) -> bool:
        if user_id in self._active:
            return False
        self._active.add(user_id)
        return True

    def finish(self, user_id: int) -> None:
        self._active.discard(user_id)


download_limiter = RateLimiter(max_calls=3, period=60)
active_downloads = ActiveDownloads()