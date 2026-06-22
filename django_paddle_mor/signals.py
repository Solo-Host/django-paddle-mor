"""Webhook lifecycle signals for django-paddle-mor."""

from django.dispatch import Signal

webhook_pre_validate = Signal()
webhook_post_validate = Signal()
webhook_pre_process = Signal()
webhook_post_process = Signal()
webhook_processing_error = Signal()
