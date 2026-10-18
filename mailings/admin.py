from django.contrib import admin

from .models import Attempt, Mailing, Message, Recipient

admin.site.register(Recipient)
admin.site.register(Message)
admin.site.register(Mailing)
admin.site.register(Attempt)
