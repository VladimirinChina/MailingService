from typing import Any

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

from .models import Attempt, Mailing, Recipient

HOME_STATS_KEY = "home_stats"
HOME_STATS_TTL = 60
USER_STATS_TTL = 60


def user_stats_key(user_id: int) -> str:
    return f"user_stats:{user_id}"


def get_home_stats() -> dict[str, Any]:
    def compute() -> dict[str, Any]:
        now = timezone.now()
        return {
            "total_mailings": Mailing.objects.count(),
            "active_mailings": Mailing.objects.filter(
                start_time__lte=now, end_time__gte=now, is_disabled=False
            ).count(),
            "unique_recipients": Recipient.objects.count(),
        }

    stats: dict[str, Any] = cache.get_or_set(HOME_STATS_KEY, compute, HOME_STATS_TTL)
    return stats


def get_user_stats(user: Any) -> dict[str, Any]:
    def compute() -> dict[str, Any]:
        totals = Attempt.objects.filter(mailing__owner=user).aggregate(
            success=Count("id", filter=Q(status=Attempt.SUCCESS)),
            fail=Count("id", filter=Q(status=Attempt.FAIL)),
        )
        per_mailing = list(
            Mailing.objects.filter(owner=user)
            .annotate(
                success_count=Count("attempts", filter=Q(attempts__status=Attempt.SUCCESS)),
                fail_count=Count("attempts", filter=Q(attempts__status=Attempt.FAIL)),
            )
            .order_by("-start_time")
            .values("pk", "status", "start_time", "success_count", "fail_count")
        )
        return {
            "success": totals["success"],
            "fail": totals["fail"],
            "sent": totals["success"],
            "per_mailing": per_mailing,
        }

    stats: dict[str, Any] = cache.get_or_set(user_stats_key(user.pk), compute, USER_STATS_TTL)
    return stats


def invalidate_home_stats() -> None:
    cache.delete(HOME_STATS_KEY)


def invalidate_user_stats(user_id: int) -> None:
    cache.delete(user_stats_key(user_id))
