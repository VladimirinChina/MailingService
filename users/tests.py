import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()
PASSWORD = "Sup3r-secret-pass"


class RegistrationTests(TestCase):
    def register(self, email: str = "new@example.com") -> None:
        self.client.post(
            reverse("users:register"),
            {"email": email, "password1": PASSWORD, "password2": PASSWORD},
        )

    def test_registration_creates_inactive_user_and_sends_email(self) -> None:
        response = self.client.post(
            reverse("users:register"),
            {"email": "new@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )
        self.assertRedirects(response, reverse("users:register_done"))
        self.assertFalse(User.objects.get(email="new@example.com").is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/users/confirm/", mail.outbox[0].body)

    def test_confirmation_link_activates_user(self) -> None:
        self.register()
        match = re.search(r"/users/confirm/\S+", mail.outbox[0].body)
        assert match is not None
        response = self.client.get(match.group(0))
        self.assertRedirects(response, reverse("users:login"))
        self.assertTrue(User.objects.get(email="new@example.com").is_active)

    def test_invalid_confirmation_link_does_not_activate_user(self) -> None:
        user = User.objects.create_user(email="x@example.com", password=PASSWORD, is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = self.client.get(reverse("users:confirm", kwargs={"uidb64": uid, "token": "bad-token"}))
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_inactive_user_cannot_log_in(self) -> None:
        User.objects.create_user(email="x@example.com", password=PASSWORD, is_active=False)
        self.assertFalse(self.client.login(email="x@example.com", password=PASSWORD))

    def test_login_and_logout(self) -> None:
        User.objects.create_user(email="x@example.com", password=PASSWORD)
        response = self.client.post(reverse("users:login"), {"username": "x@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("mailings:home"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)
        self.client.post(reverse("users:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_reset_sends_email(self) -> None:
        User.objects.create_user(email="x@example.com", password=PASSWORD)
        response = self.client.post(reverse("users:password_reset"), {"email": "x@example.com"})
        self.assertRedirects(response, reverse("users:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/users/reset/", mail.outbox[0].body)


class ManagerTests(TestCase):
    def setUp(self) -> None:
        call_command("create_manager_group", stdout=StringIO())
        self.manager = User.objects.create_user(email="manager@example.com", password=PASSWORD)
        self.manager.groups.add(Group.objects.get(name="Менеджеры"))
        self.user = User.objects.create_user(email="user@example.com", password=PASSWORD)

    def test_regular_user_cannot_see_user_list(self) -> None:
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("users:user_list")).status_code, 403)

    def test_manager_sees_user_list(self) -> None:
        self.client.force_login(self.manager)
        response = self.client.get(reverse("users:user_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user@example.com")

    def test_manager_can_block_and_unblock_user(self) -> None:
        self.client.force_login(self.manager)
        url = reverse("users:user_toggle", args=[self.user.pk])
        self.client.post(url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.client.post(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_manager_cannot_block_superuser_or_self(self) -> None:
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(self.manager)
        self.client.post(reverse("users:user_toggle", args=[admin.pk]))
        self.client.post(reverse("users:user_toggle", args=[self.manager.pk]))
        admin.refresh_from_db()
        self.manager.refresh_from_db()
        self.assertTrue(admin.is_active)
        self.assertTrue(self.manager.is_active)

    def test_regular_user_cannot_block_users(self) -> None:
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        self.client.force_login(self.user)
        response = self.client.post(reverse("users:user_toggle", args=[other.pk]))
        self.assertEqual(response.status_code, 403)
        other.refresh_from_db()
        self.assertTrue(other.is_active)
