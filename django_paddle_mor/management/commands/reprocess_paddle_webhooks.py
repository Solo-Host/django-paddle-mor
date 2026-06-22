from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from django_paddle_mor.event_handlers import PENDING_WEBHOOK_LEASE, reprocess_webhook_event
from django_paddle_mor.models import WebhookEvent


class Command(BaseCommand):
    help = "Reprocess failed or selected Paddle webhook events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--event-id",
            action="append",
            dest="event_ids",
            help="A webhook event_id to reprocess. Repeat for multiple values.",
        )
        parser.add_argument(
            "--dedupe-key",
            action="append",
            dest="dedupe_keys",
            help="A webhook dedupe key to reprocess. Repeat for multiple values.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of webhook events to reprocess.",
        )

    def handle(self, *args, **options):
        event_ids = options["event_ids"] or []
        dedupe_keys = options["dedupe_keys"] or []
        limit = options["limit"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be >= 1.")

        queryset = WebhookEvent.objects.all().order_by("processed_at", "id")
        if event_ids:
            queryset = queryset.filter(event_id__in=event_ids)
        if dedupe_keys:
            queryset = queryset.filter(dedupe_key__in=dedupe_keys)
        if not event_ids and not dedupe_keys:
            stale_pending_cutoff = timezone.now() - PENDING_WEBHOOK_LEASE
            queryset = queryset.filter(
                Q(processing_state=WebhookEvent.ProcessingState.FAILED)
                | Q(
                    processing_state=WebhookEvent.ProcessingState.PENDING,
                    processed_at__lt=stale_pending_cutoff,
                )
            )
        if limit is not None:
            queryset = queryset[:limit]

        events = list(queryset)
        if not events:
            self.stdout.write("No webhook events matched the selection.")
            return

        for webhook_event in events:
            result = reprocess_webhook_event(webhook_event)
            identifier = result.webhook_event.event_id or result.webhook_event.dedupe_key
            self.stdout.write(
                f"{identifier}: {result.webhook_event.processing_state}"
            )
