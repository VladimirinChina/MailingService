from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_home_stats, invalidate_user_stats
from .models import Mailing, Recipient


@receiver([post_save, post_delete], sender=Mailing)
def mailing_changed(sender, instance, **kwargs):
    invalidate_home_stats()
    invalidate_user_stats(instance.owner_id)


@receiver([post_save, post_delete], sender=Recipient)
def recipient_changed(sender, **kwargs):
    invalidate_home_stats()
