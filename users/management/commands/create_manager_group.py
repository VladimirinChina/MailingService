from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создаёт группу «Менеджеры» с нужными правами"

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name="Менеджеры")
        codenames = [
            "can_view_all_mailings",
            "can_disable_mailings",
            "can_view_all_users",
            "can_block_users",
        ]
        group.permissions.set(Permission.objects.filter(codename__in=codenames))
        self.stdout.write(self.style.SUCCESS(f"Группа «{group.name}» готова, прав: {group.permissions.count()}"))
