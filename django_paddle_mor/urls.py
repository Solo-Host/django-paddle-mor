from django.urls import path

from .views import paddle_webhook

app_name = "django_paddle_mor"

urlpatterns = [
    path("webhooks/paddle/", paddle_webhook, name="paddle_webhook"),
]
