from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_paddle_mor.exceptions import NonPersistedResourceError, UnsupportedResourceError
from django_paddle_mor.registry import PERSISTED_RESOURCE_NAMES, resolve_resource_name
from django_paddle_mor.sync import sync_all_resources, sync_resource


class Command(BaseCommand):
    help = "Synchronize Paddle Billing resources into local Django models."

    def add_arguments(self, parser):
        parser.add_argument("resource", help="A resource name or 'all'.")
        parser.add_argument(
            "lookup",
            nargs="*",
            help="Optional lookup identifiers passed to the SDK get() call for a single resource.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of records to sync when using list-based synchronization.",
        )

    def handle(self, *args, **options):
        resource_name = options["resource"]
        lookup = options["lookup"]
        limit = options["limit"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be >= 1.")

        if resource_name == "all":
            if lookup:
                raise CommandError("Lookup identifiers cannot be used when resource='all'.")
            results = sync_all_resources(limit=limit)
            for synced_resource_name, synced_count in sorted(results.items()):
                self.stdout.write(f"{synced_resource_name}: {synced_count}")
            return

        try:
            canonical_name = resolve_resource_name(resource_name)
        except UnsupportedResourceError as exc:
            raise CommandError(str(exc)) from exc

        if canonical_name not in PERSISTED_RESOURCE_NAMES:
            raise CommandError(f"{canonical_name} is not a persisted Django model resource.")

        try:
            synced_instances = sync_resource(canonical_name, lookup=lookup, limit=limit)
        except (NonPersistedResourceError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Synced {len(synced_instances)} {canonical_name} record(s).")
