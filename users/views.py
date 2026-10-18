from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import CreateView, ListView, View

from .forms import UserRegisterForm

User = get_user_model()


def send_confirmation_email(request: HttpRequest, user: Any) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = request.build_absolute_uri(reverse("users:confirm", kwargs={"uidb64": uid, "token": token}))
    send_mail(
        subject="Подтверждение регистрации",
        message=f"Здравствуйте!\n\nЧтобы завершить регистрацию, подтвердите email по ссылке:\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


class RegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = "users/form.html"
    success_url = reverse_lazy("users:register_done")
    extra_context = {"title": "Регистрация", "button": "Зарегистрироваться"}

    def form_valid(self, form: Any) -> HttpResponse:
        user = form.save(commit=False)
        user.is_active = False
        user.save()
        send_confirmation_email(self.request, user)
        return redirect(self.success_url)


def confirm_email(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except TypeError, ValueError, OverflowError, User.DoesNotExist:
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Email подтверждён. Теперь можно войти.")
        return redirect("users:login")

    return render(
        request,
        "users/message.html",
        {"title": "Ссылка недействительна", "text": "Ссылка подтверждения неверна или устарела."},
    )


class UserListView(PermissionRequiredMixin, ListView):
    model = User
    permission_required = "users.can_view_all_users"
    template_name = "users/user_list.html"
    ordering = ["email"]


class ToggleUserActiveView(PermissionRequiredMixin, View):
    permission_required = "users.can_block_users"

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk or target.is_superuser:
            messages.error(request, "Этого пользователя заблокировать нельзя.")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            state = "разблокирован" if target.is_active else "заблокирован"
            messages.success(request, f"Пользователь {target.email} {state}.")
        return redirect("users:user_list")
