from datetime import timedelta
from io import StringIO
from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .cache import get_home_stats, get_user_stats
from .forms import RecipientForm
from .models import Attempt, Mailing, Message, Recipient
from .services import MailingNotAllowed, send_mailing

User = get_user_model()

LOCMEM_CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
PASSWORD = "Sup3r-secret-pass"

HOUR = timedelta(hours=1)


def create_user(email: str) -> Any:
    return User.objects.create_user(email=email, password=PASSWORD)


def create_mailing(owner: Any, start: timedelta, end: timedelta, recipients: int = 2) -> Mailing:
    now = timezone.now()
    message = Message.objects.create(owner=owner, subject="Тема", body="Текст письма")
    mailing = Mailing.objects.create(owner=owner, start_time=now + start, end_time=now + end, message=message)
    for index in range(recipients):
        recipient = Recipient.objects.create(
            owner=owner, email=f"client{index}@example.com", full_name=f"Клиент {index}"
        )
        mailing.recipients.add(recipient)
    return mailing


@override_settings(CACHES=LOCMEM_CACHES)
class BaseTestCase(TestCase):
    """Каждый тест работает с кешем в памяти, а не с Redis из .env."""

    def setUp(self) -> None:
        cache.clear()
        self.owner = create_user("owner@example.com")


class MailingModelTests(BaseTestCase):
    def build(self, start: timedelta, end: timedelta) -> Mailing:
        now = timezone.now()
        message = Message.objects.create(owner=self.owner, subject="Тема", body="Текст")
        return Mailing(owner=self.owner, start_time=now + start, end_time=now + end, message=message)

    def test_start_in_past_is_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            self.build(-HOUR, HOUR).clean()

    def test_start_must_be_before_end(self) -> None:
        with self.assertRaises(ValidationError):
            self.build(2 * HOUR, HOUR).clean()

    def test_valid_period_passes(self) -> None:
        self.build(HOUR, 2 * HOUR).clean()

    def test_status_is_computed_by_time(self) -> None:
        self.assertEqual(self.build(HOUR, 2 * HOUR).compute_status(), Mailing.CREATED)
        self.assertEqual(self.build(-HOUR, HOUR).compute_status(), Mailing.STARTED)
        self.assertEqual(self.build(-2 * HOUR, -HOUR).compute_status(), Mailing.FINISHED)


class RecipientTests(BaseTestCase):
    def test_same_email_is_allowed_for_different_owners(self) -> None:
        other = create_user("other@example.com")
        Recipient.objects.create(owner=self.owner, email="client@example.com", full_name="А")
        Recipient.objects.create(owner=other, email="client@example.com", full_name="Б")
        self.assertEqual(Recipient.objects.filter(email="client@example.com").count(), 2)

    def test_duplicate_email_for_same_owner_is_rejected_by_database(self) -> None:
        Recipient.objects.create(owner=self.owner, email="client@example.com", full_name="А")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Recipient.objects.create(owner=self.owner, email="client@example.com", full_name="Б")

    def test_form_rejects_duplicate_email_for_same_owner(self) -> None:
        Recipient.objects.create(owner=self.owner, email="client@example.com", full_name="А")
        form = RecipientForm(data={"email": "client@example.com", "full_name": "Б", "comment": ""}, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_form_allows_editing_existing_recipient(self) -> None:
        recipient = Recipient.objects.create(owner=self.owner, email="client@example.com", full_name="А")
        form = RecipientForm(
            data={"email": "client@example.com", "full_name": "Новое имя", "comment": ""},
            instance=recipient,
            user=self.owner,
        )
        self.assertTrue(form.is_valid())


class SendMailingTests(BaseTestCase):
    def test_send_inside_period_reaches_all_recipients(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR)
        ok, failed = send_mailing(mailing)
        self.assertEqual((ok, failed), (2, 0))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Attempt.objects.filter(mailing=mailing, status=Attempt.SUCCESS).count(), 2)
        mailing.refresh_from_db()
        self.assertEqual(mailing.status, Mailing.STARTED)

    def test_send_before_start_is_forbidden(self) -> None:
        mailing = create_mailing(self.owner, HOUR, 2 * HOUR)
        with self.assertRaises(MailingNotAllowed):
            send_mailing(mailing)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_send_after_end_is_forbidden(self) -> None:
        mailing = create_mailing(self.owner, -2 * HOUR, -HOUR)
        with self.assertRaises(MailingNotAllowed):
            send_mailing(mailing)
        self.assertEqual(len(mail.outbox), 0)

    def test_disabled_mailing_is_not_sent(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR)
        mailing.is_disabled = True
        mailing.save()
        with self.assertRaises(MailingNotAllowed):
            send_mailing(mailing)
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_send_creates_unsuccessful_attempts(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR)
        with patch("mailings.services.send_mail", side_effect=OSError("SMTP недоступен")):
            ok, failed = send_mailing(mailing)
        self.assertEqual((ok, failed), (0, 2))
        attempts = Attempt.objects.filter(mailing=mailing)
        self.assertEqual(attempts.filter(status=Attempt.FAIL).count(), 2)
        self.assertTrue(all("SMTP недоступен" in attempt.server_response for attempt in attempts))

    def test_attempts_are_created_with_one_insert(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR, recipients=3)
        with CaptureQueriesContext(connection) as context:
            send_mailing(mailing)
        inserts = [q for q in context.captured_queries if q["sql"].startswith('INSERT INTO "mailings_attempt"')]
        self.assertEqual(len(inserts), 1)

    def test_command_sends_mailing(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR)
        call_command("send_mailing", mailing.pk, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)

    def test_command_fails_outside_period(self) -> None:
        mailing = create_mailing(self.owner, HOUR, 2 * HOUR)
        with self.assertRaises(CommandError):
            call_command("send_mailing", mailing.pk, stdout=StringIO())


class AccessTests(BaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other = create_user("other@example.com")
        self.manager = create_user("manager@example.com")
        call_command("create_manager_group", stdout=StringIO())
        self.manager.groups.add(Group.objects.get(name="Менеджеры"))
        self.own_mailing = create_mailing(self.owner, -HOUR, HOUR)
        self.foreign_mailing = create_mailing(self.other, -HOUR, HOUR)

    def url(self, name: str, mailing: Mailing) -> str:
        return reverse(f"mailings:{name}", args=[mailing.pk])

    def test_anonymous_is_redirected_to_login(self) -> None:
        list_url = reverse("mailings:mailing_list")
        response = self.client.get(list_url)
        self.assertRedirects(response, f"{reverse('users:login')}?next={list_url}")

    def test_user_sees_only_own_mailings(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.get(reverse("mailings:mailing_list"))
        self.assertEqual([m.pk for m in response.context["object_list"]], [self.own_mailing.pk])

    def test_user_cannot_view_or_change_foreign_mailing(self) -> None:
        self.client.force_login(self.owner)
        for name in ("mailing_detail", "mailing_update", "mailing_delete"):
            self.assertEqual(self.client.get(self.url(name, self.foreign_mailing)).status_code, 404)
        self.assertEqual(self.client.post(self.url("mailing_delete", self.foreign_mailing)).status_code, 404)
        self.assertTrue(Mailing.objects.filter(pk=self.foreign_mailing.pk).exists())

    def test_user_cannot_send_foreign_mailing(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.post(self.url("mailing_send", self.foreign_mailing))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_user_can_send_own_mailing(self) -> None:
        self.client.force_login(self.owner)
        self.client.post(self.url("mailing_send", self.own_mailing))
        self.assertEqual(len(mail.outbox), 2)

    def test_manager_sees_all_mailings(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(reverse("mailings:mailing_list"))
        shown = {m.pk for m in response.context["object_list"]}
        self.assertEqual(shown, {self.own_mailing.pk, self.foreign_mailing.pk})

    def test_manager_can_view_but_not_change_foreign_mailing(self) -> None:
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url("mailing_detail", self.foreign_mailing)).status_code, 200)
        self.assertEqual(self.client.get(self.url("mailing_update", self.foreign_mailing)).status_code, 404)
        self.assertEqual(self.client.post(self.url("mailing_delete", self.foreign_mailing)).status_code, 404)
        self.assertTrue(Mailing.objects.filter(pk=self.foreign_mailing.pk).exists())

    def test_manager_can_disable_and_enable_mailing(self) -> None:
        self.client.force_login(self.manager)
        url = self.url("mailing_toggle", self.foreign_mailing)
        self.client.post(url)
        self.foreign_mailing.refresh_from_db()
        self.assertTrue(self.foreign_mailing.is_disabled)
        self.client.post(url)
        self.foreign_mailing.refresh_from_db()
        self.assertFalse(self.foreign_mailing.is_disabled)

    def test_regular_user_cannot_disable_mailing(self) -> None:
        self.client.force_login(self.owner)
        response = self.client.post(self.url("mailing_toggle", self.own_mailing))
        self.assertEqual(response.status_code, 403)
        self.own_mailing.refresh_from_db()
        self.assertFalse(self.own_mailing.is_disabled)

    def test_owner_cannot_send_disabled_mailing(self) -> None:
        self.own_mailing.is_disabled = True
        self.own_mailing.save()
        self.client.force_login(self.owner)
        self.client.post(self.url("mailing_send", self.own_mailing))
        self.assertEqual(len(mail.outbox), 0)


class CacheTests(BaseTestCase):
    def test_home_stats_are_served_from_cache(self) -> None:
        with self.assertNumQueries(3):
            get_home_stats()
        with self.assertNumQueries(0):
            get_home_stats()

    def test_home_stats_reset_when_data_changes(self) -> None:
        self.assertEqual(get_home_stats()["unique_recipients"], 0)
        Recipient.objects.create(owner=self.owner, email="new@example.com", full_name="Новый")
        self.assertEqual(get_home_stats()["unique_recipients"], 1)

    def test_unique_recipients_counts_distinct_emails(self) -> None:
        other = create_user("other@example.com")
        Recipient.objects.create(owner=self.owner, email="same@example.com", full_name="А")
        Recipient.objects.create(owner=other, email="same@example.com", full_name="Б")
        self.assertEqual(get_home_stats()["unique_recipients"], 1)

    def test_user_stats_reset_after_sending(self) -> None:
        mailing = create_mailing(self.owner, -HOUR, HOUR)
        self.assertEqual(get_user_stats(self.owner)["success"], 0)
        send_mailing(mailing)
        self.assertEqual(get_user_stats(self.owner)["success"], 2)

    def test_home_page_has_client_cache_headers(self) -> None:
        response = self.client.get(reverse("mailings:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=60", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
