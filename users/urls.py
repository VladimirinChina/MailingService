from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import TemplateView

from . import views
from .forms import LoginForm, NewPasswordForm, ResetForm

app_name = "users"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="users/login.html", authentication_form=LoginForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path(
        "register/done/",
        TemplateView.as_view(
            template_name="users/message.html",
            extra_context={
                "title": "Проверьте почту",
                "text": "Мы отправили письмо со ссылкой для подтверждения email.",
            },
        ),
        name="register_done",
    ),
    path("confirm/<uidb64>/<token>/", views.confirm_email, name="confirm"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=ResetForm,
            template_name="users/form.html",
            email_template_name="users/password_reset_email.txt",
            subject_template_name="users/password_reset_subject.txt",
            success_url=reverse_lazy("users:password_reset_done"),
            extra_context={"title": "Восстановление пароля", "button": "Отправить ссылку"},
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/message.html",
            extra_context={
                "title": "Письмо отправлено",
                "text": "Если такой email зарегистрирован, мы отправили на него ссылку для смены пароля.",
            },
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=NewPasswordForm,
            template_name="users/form.html",
            success_url=reverse_lazy("users:password_reset_complete"),
            extra_context={"title": "Новый пароль", "button": "Сохранить пароль"},
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/message.html",
            extra_context={
                "title": "Пароль изменён",
                "text": "Теперь можно войти с новым паролем.",
                "link_url": reverse_lazy("users:login"),
                "link_text": "Войти",
            },
        ),
        name="password_reset_complete",
    ),
    path("list/", views.UserListView.as_view(), name="user_list"),
    path("<int:pk>/toggle/", views.ToggleUserActiveView.as_view(), name="user_toggle"),
]
