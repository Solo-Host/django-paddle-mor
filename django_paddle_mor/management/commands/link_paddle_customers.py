from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_paddle_mor.models import Customer
from django_paddle_mor.subscriber import (
    link_customer_to_subscriber,
    validate_subscriber_model_configuration,
)


class Command(BaseCommand):
    help = "Link synced Paddle customers to the configured subscriber model by email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customer-id",
            action="append",
            dest="customer_ids",
            help="A Paddle customer id to link. Repeat for multiple values.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of customers to inspect.",
        )

    def handle(self, *args, **options):
        if validate_subscriber_model_configuration() is None:
            raise CommandError(
                "Configure DJANGO_PADDLE_MOR['SUBSCRIBER_MODEL'] before linking Paddle customers."
            )

        limit = options["limit"]
        if limit is not None and limit < 1:
            raise CommandError("--limit must be >= 1.")

        queryset = Customer.objects.filter(email__gt="").order_by("paddle_id")
        customer_ids = options["customer_ids"] or []
        if customer_ids:
            queryset = queryset.filter(paddle_id__in=customer_ids)
        if limit is not None:
            queryset = queryset[:limit]

        linked = 0
        inspected = 0
        for customer in queryset:
            inspected += 1
            subscriber = link_customer_to_subscriber(customer)
            if subscriber is not None:
                linked += 1
                self.stdout.write(f"{customer.paddle_id}: linked to {subscriber}")

        self.stdout.write(f"Linked {linked} of {inspected} inspected customer(s).")
