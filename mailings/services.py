from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Attempt, Mailing


class MailingNotAllowed(Exception):
    """Отправка рассылки сейчас запрещена."""


def refresh_statuses() -> None:
    now = timezone.now()
    Mailing.objects.filter(start_time__gt=now).exclude(status=Mailing.CREATED).update(status=Mailing.CREATED)
    Mailing.objects.filter(start_time__lte=now, end_time__gte=now).exclude(status=Mailing.STARTED).update(
        status=Mailing.STARTED
    )
    Mailing.objects.filter(end_time__lt=now).exclude(status=Mailing.FINISHED).update(status=Mailing.FINISHED)


def send_mailing(mailing: Mailing) -> tuple[int, int]:
    """Отправляет рассылку всем получателям. Возвращает (успешно, неуспешно)."""
    mailing.update_status()
    if mailing.is_disabled:
        raise MailingNotAllowed("Рассылка отключена менеджером.")
    if not mailing.can_send_now():
        raise MailingNotAllowed("Сейчас вне периода рассылки, отправка запрещена.")

    attempts = []
    for recipient in mailing.recipients.all():
        try:
            send_mail(
                subject=mailing.message.subject,
                message=mailing.message.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
        except Exception as exc:
            attempts.append(
                Attempt(mailing=mailing, status=Attempt.FAIL, server_response=f"{recipient.email}: {exc}")
            )
        else:
            attempts.append(
                Attempt(
                    mailing=mailing,
                    status=Attempt.SUCCESS,
                    server_response=f"{recipient.email}: письмо принято почтовым сервером",
                )
            )
    Attempt.objects.bulk_create(attempts)
    ok = sum(1 for a in attempts if a.status == Attempt.SUCCESS)
    return ok, len(attempts) - ok
