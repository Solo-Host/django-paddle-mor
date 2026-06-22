from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_paddle_mor.models import WebhookEvent


class Command(BaseCommand):
    help = "Delete old Paddle webhook events by state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--state",
            choices=[choice for choice, _label in WebhookEvent.ProcessingState.choices],
            default=WebhookEvent.ProcessingState.PROCESSED,
            help="Webhook processing state to clear.",
        )
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=30,
            help="Only clear webhook events older than this many days.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many events would be cleared without deleting them.",
        )

    def handle(self, *args, **options):
        older_than_days = options["older_than_days"]
        if older_than_days < 0:
            raise CommandError("--older-than-days must be >= 0.")

        cutoff = timezone.now() - timedelta(days=older_than_days)
        queryset = WebhookEvent.objects.filter(
            processing_state=options["state"],
            processed_at__lt=cutoff,
        )
        count = queryset.count()

        if options["dry_run"]:
            self.stdout.write(f"{count} webhook event(s) would be deleted.")
            return

        queryset.delete()
        self.stdout.write(f"Deleted {count} webhook event(s).")
