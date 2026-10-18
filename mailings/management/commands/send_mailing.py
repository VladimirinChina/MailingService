from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from mailings.models import Mailing
from mailings.services import MailingNotAllowed, send_mailing


class Command(BaseCommand):
    help = "Отправить рассылку по её ID"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("mailing_id", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            mailing = Mailing.objects.get(pk=options["mailing_id"])
        except Mailing.DoesNotExist:
            raise CommandError("Рассылка не найдена")
        try:
            ok, failed = send_mailing(mailing)
        except MailingNotAllowed as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Успешно: {ok}, не успешно: {failed}"))
