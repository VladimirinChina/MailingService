from typing import Any

from django import forms

from .models import Mailing, Message, Recipient


class BootstrapMixin(forms.BaseForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)


class RecipientForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Recipient
        fields = ["email", "full_name", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"]
        if self.user is not None:
            duplicates = Recipient.objects.filter(owner=self.user, email=email)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError("У вас уже есть получатель с таким email.")
        return email


class MessageForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ["subject", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 6})}


class MailingForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Mailing
        fields = ["start_time", "end_time", "message", "recipients"]
        widgets = {
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["message"].queryset = Message.objects.filter(owner=user)
            self.fields["recipients"].queryset = Recipient.objects.filter(owner=user)
