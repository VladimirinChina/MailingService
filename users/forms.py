from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm

from mailings.forms import BootstrapMixin

from .models import User


class UserRegisterForm(BootstrapMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)


class LoginForm(BootstrapMixin, AuthenticationForm):
    pass


class ResetForm(BootstrapMixin, PasswordResetForm):
    pass


class NewPasswordForm(BootstrapMixin, SetPasswordForm):
    pass
