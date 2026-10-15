from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count
from django.db.models.query_utils import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import MailingForm, MessageForm, RecipientForm
from .models import Mailing, Message, Recipient, Attempt
from .services import MailingNotAllowed, refresh_statuses, send_mailing


class VisibleQuerysetMixin(LoginRequiredMixin):
    """Пользователь видит своё, менеджер (с правом) видит всё."""

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.has_perm("mailings.can_view_all_mailings"):
            return qs
        return qs.filter(owner=self.request.user)


class OwnQuerysetMixin(LoginRequiredMixin):
    """Менять и удалять можно только свои объекты."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class OwnerFormMixin:
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


# ---------- Главная ----------
class HomeView(TemplateView):
    template_name = "mailings/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        refresh_statuses()
        now = timezone.now()
        context["total_mailings"] = Mailing.objects.count()
        context["active_mailings"] = Mailing.objects.filter(
            status=Mailing.STARTED, start_time__lte=now, end_time__gte=now, is_disabled=False
        ).count()
        context["unique_recipients"] = Recipient.objects.count()
        return context


# ---------- Получатели ----------
class RecipientListView(VisibleQuerysetMixin, ListView):
    model = Recipient


class RecipientCreateView(LoginRequiredMixin, OwnerFormMixin, CreateView):
    model = Recipient
    form_class = RecipientForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:recipient_list")
    extra_context = {"title": "Новый получатель"}


class RecipientUpdateView(OwnQuerysetMixin, UpdateView):
    model = Recipient
    form_class = RecipientForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:recipient_list")
    extra_context = {"title": "Редактирование получателя"}


class RecipientDeleteView(OwnQuerysetMixin, DeleteView):
    model = Recipient
    template_name = "mailings/confirm_delete.html"
    success_url = reverse_lazy("mailings:recipient_list")


# ---------- Сообщения ----------
class MessageListView(VisibleQuerysetMixin, ListView):
    model = Message


class MessageCreateView(LoginRequiredMixin, OwnerFormMixin, CreateView):
    model = Message
    form_class = MessageForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:message_list")
    extra_context = {"title": "Новое сообщение"}


class MessageUpdateView(OwnQuerysetMixin, UpdateView):
    model = Message
    form_class = MessageForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:message_list")
    extra_context = {"title": "Редактирование сообщения"}


class MessageDeleteView(OwnQuerysetMixin, DeleteView):
    model = Message
    template_name = "mailings/confirm_delete.html"
    success_url = reverse_lazy("mailings:message_list")


# ---------- Рассылки ----------
class MailingListView(VisibleQuerysetMixin, ListView):
    model = Mailing

    def get_queryset(self):
        refresh_statuses()
        return super().get_queryset().select_related("message").annotate(recipients_count=Count("recipients"))


class MailingDetailView(VisibleQuerysetMixin, DetailView):
    model = Mailing

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.update_status()
        return obj


class MailingFormKwargsMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class MailingCreateView(LoginRequiredMixin, MailingFormKwargsMixin, OwnerFormMixin, CreateView):
    model = Mailing
    form_class = MailingForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:mailing_list")
    extra_context = {"title": "Новая рассылка"}


class MailingUpdateView(OwnQuerysetMixin, MailingFormKwargsMixin, UpdateView):
    model = Mailing
    form_class = MailingForm
    template_name = "mailings/form.html"
    success_url = reverse_lazy("mailings:mailing_list")
    extra_context = {"title": "Редактирование рассылки"}


class MailingDeleteView(OwnQuerysetMixin, DeleteView):
    model = Mailing
    template_name = "mailings/confirm_delete.html"
    success_url = reverse_lazy("mailings:mailing_list")


class MailingSendView(LoginRequiredMixin, View):
    def post(self, request, pk):
        mailing = get_object_or_404(Mailing, pk=pk, owner=request.user)
        try:
            ok, failed = send_mailing(mailing)
        except MailingNotAllowed as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Отправка завершена. Успешно: {ok}, не успешно: {failed}.")
        return redirect("mailings:mailing_detail", pk=pk)


class StatisticsView(LoginRequiredMixin, TemplateView):
    template_name = "mailings/statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        totals = Attempt.objects.filter(mailing__owner=user).aggregate(
            success=Count("id", filter=Q(status=Attempt.SUCCESS)),
            fail=Count("id", filter=Q(status=Attempt.FAIL)),
        )
        context["success"] = totals["success"]
        context["fail"] = totals["fail"]
        context["sent"] = totals["success"]  # отправленные сообщения = успешные попытки
        context["per_mailing"] = (
            Mailing.objects.filter(owner=user)
            .annotate(
                success_count=Count("attempts", filter=Q(attempts__status=Attempt.SUCCESS)),
                fail_count=Count("attempts", filter=Q(attempts__status=Attempt.FAIL)),
            )
            .order_by("-start_time")
        )
        return context


class MailingToggleDisabledView(PermissionRequiredMixin, View):
    permission_required = "mailings.can_disable_mailings"

    def post(self, request, pk):
        mailing = get_object_or_404(Mailing, pk=pk)
        mailing.is_disabled = not mailing.is_disabled
        mailing.save(update_fields=["is_disabled"])
        state = "отключена" if mailing.is_disabled else "снова включена"
        messages.success(request, f"Рассылка #{mailing.pk} {state}.")
        return redirect("mailings:mailing_detail", pk=pk)
