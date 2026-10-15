from django.urls import path

from . import views

app_name = "mailings"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("recipients/", views.RecipientListView.as_view(), name="recipient_list"),
    path("recipients/create/", views.RecipientCreateView.as_view(), name="recipient_create"),
    path("recipients/<int:pk>/edit/", views.RecipientUpdateView.as_view(), name="recipient_update"),
    path("recipients/<int:pk>/delete/", views.RecipientDeleteView.as_view(), name="recipient_delete"),
    path("messages/", views.MessageListView.as_view(), name="message_list"),
    path("messages/create/", views.MessageCreateView.as_view(), name="message_create"),
    path("messages/<int:pk>/edit/", views.MessageUpdateView.as_view(), name="message_update"),
    path("messages/<int:pk>/delete/", views.MessageDeleteView.as_view(), name="message_delete"),
    path("mailings/", views.MailingListView.as_view(), name="mailing_list"),
    path("mailings/create/", views.MailingCreateView.as_view(), name="mailing_create"),
    path("mailings/<int:pk>/", views.MailingDetailView.as_view(), name="mailing_detail"),
    path("mailings/<int:pk>/edit/", views.MailingUpdateView.as_view(), name="mailing_update"),
    path("mailings/<int:pk>/delete/", views.MailingDeleteView.as_view(), name="mailing_delete"),
    path("mailings/<int:pk>/send/", views.MailingSendView.as_view(), name="mailing_send"),
    path("statistics/", views.StatisticsView.as_view(), name="statistics"),
    path("mailings/<int:pk>/toggle/", views.MailingToggleDisabledView.as_view(), name="mailing_toggle"),
]
