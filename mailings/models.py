from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Recipient(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipients", verbose_name="Владелец"
    )
    email = models.EmailField("Email", unique=True)
    full_name = models.CharField("Ф. И. О.", max_length=255)
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Получатель"
        verbose_name_plural = "Получатели"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"


class Message(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages", verbose_name="Владелец"
    )
    subject = models.CharField("Тема письма", max_length=255)
    body = models.TextField("Тело письма")

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.subject


class Mailing(models.Model):
    CREATED = "Создана"
    STARTED = "Запущена"
    FINISHED = "Завершена"
    STATUS_CHOICES = [(CREATED, CREATED), (STARTED, STARTED), (FINISHED, FINISHED)]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mailings", verbose_name="Владелец"
    )
    start_time = models.DateTimeField("Начало отправки")
    end_time = models.DateTimeField("Окончание отправки")
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=CREATED)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="mailings", verbose_name="Сообщение")
    recipients = models.ManyToManyField(Recipient, related_name="mailings", verbose_name="Получатели")
    is_disabled = models.BooleanField("Отключена менеджером", default=False)

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"
        ordering = ["-start_time"]
        permissions = [
            ("can_view_all_mailings", "Может просматривать все рассылки"),
            ("can_disable_mailings", "Может отключать рассылки"),
        ]

    def __str__(self) -> str:
        return f"Рассылка #{self.pk} ({self.status})"

    def clean(self) -> None:
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("Время начала должно быть раньше времени окончания.")
        if self.start_time and self.pk is None and self.start_time < timezone.now():
            raise ValidationError("Время начала не может быть в прошлом.")

    def compute_status(self) -> str:
        now = timezone.now()
        if now < self.start_time:
            return self.CREATED
        if now <= self.end_time:
            return self.STARTED
        return self.FINISHED

    def update_status(self) -> None:
        new_status = self.compute_status()
        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=["status"])

    def can_send_now(self) -> bool:
        return self.start_time <= timezone.now() <= self.end_time and not self.is_disabled


class Attempt(models.Model):
    SUCCESS = "Успешно"
    FAIL = "Не успешно"
    STATUS_CHOICES = [(SUCCESS, SUCCESS), (FAIL, FAIL)]

    attempt_time = models.DateTimeField("Дата и время попытки", auto_now_add=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES)
    server_response = models.TextField("Ответ почтового сервера", blank=True)
    mailing = models.ForeignKey(Mailing, on_delete=models.CASCADE, related_name="attempts", verbose_name="Рассылка")

    class Meta:
        verbose_name = "Попытка рассылки"
        verbose_name_plural = "Попытки рассылок"
        ordering = ["-attempt_time"]

    def __str__(self) -> str:
        return f"{self.mailing_id}: {self.status}"
