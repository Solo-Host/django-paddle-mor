from __future__ import annotations

from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from django_paddle_mor.event_handlers import PENDING_WEBHOOK_LEASE, ingest_webhook_payload
from django_paddle_mor.models import WebhookEndpoint, WebhookEvent
from django_paddle_mor.signals import (
    webhook_post_process,
    webhook_post_validate,
    webhook_pre_process,
    webhook_pre_validate,
    webhook_processing_error,
)


@pytest.mark.django_db
def test_endpoint_specific_webhook_route_uses_endpoint_secret_and_tracks_endpoint(
    client,
    monkeypatch,
):
    endpoint = WebhookEndpoint.objects.create(label="Primary endpoint", secret="whsec_endpoint")
    captured = {}

    def fake_verify(self, request, *, verify_time_drift=True, secrets=None):
        captured["secrets"] = secrets
        return True

    monkeypatch.setattr("django_paddle_mor.views.PaddleAPI.verify_webhook", fake_verify)

    response = client.post(
        reverse(
            "django_paddle_mor:paddle_webhook_by_uuid",
            kwargs={"endpoint_uuid": endpoint.uuid},
        ),
        data='{"event_id":"evt_endpoint","event_type":"product.updated","data":{"id":"pro_endpoint"}}',
        content_type="application/json",
    )

    webhook_event = WebhookEvent.objects.get(event_id="evt_endpoint")
    assert response.status_code == 200
    assert captured["secrets"] == ("whsec_endpoint",)
    assert webhook_event.endpoint == endpoint
    assert webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED
    assert webhook_event.processing_attempts == 1


@pytest.mark.django_db
def test_same_event_id_can_be_stored_for_different_endpoints():
    endpoint_one = WebhookEndpoint.objects.create(label="Endpoint One", secret="whsec_one")
    endpoint_two = WebhookEndpoint.objects.create(label="Endpoint Two", secret="whsec_two")

    ingest_webhook_payload(
        {"event_id": "evt_shared", "event_type": "product.updated", "data": {"id": "pro_one"}},
        endpoint=endpoint_one,
    )
    ingest_webhook_payload(
        {"event_id": "evt_shared", "event_type": "product.updated", "data": {"id": "pro_two"}},
        endpoint=endpoint_two,
    )

    assert WebhookEvent.objects.filter(event_id="evt_shared").count() == 2


@pytest.mark.django_db
def test_duplicate_processed_delivery_does_not_overwrite_success(monkeypatch):
    first_result = ingest_webhook_payload(
        {
            "event_id": "evt_duplicate_processed",
            "event_type": "product.updated",
            "data": {"id": "pro_duplicate"},
        }
    )
    assert first_result.webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED

    monkeypatch.setattr(
        "django_paddle_mor.event_handlers.sync_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("late failure")),
    )
    second_result = ingest_webhook_payload(
        {
            "event_id": "evt_duplicate_processed",
            "event_type": "product.updated",
            "data": {"id": "pro_duplicate"},
        }
    )

    webhook_event = WebhookEvent.objects.get(event_id="evt_duplicate_processed")
    assert second_result.sync_error == ""
    assert webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED
    assert webhook_event.processing_attempts == 1


@pytest.mark.django_db
def test_duplicate_pending_delivery_short_circuits_without_reprocessing(monkeypatch):
    webhook_event = WebhookEvent.objects.create(
        dedupe_key="event:global:evt_pending",
        dedupe_scope="global",
        event_id="evt_pending",
        event_type="product.updated",
        resource_name="products",
        processing_state=WebhookEvent.ProcessingState.PENDING,
        processing_attempts=1,
        payload={
            "event_id": "evt_pending",
            "event_type": "product.updated",
            "data": {"id": "pro_pending"},
        },
    )

    monkeypatch.setattr(
        "django_paddle_mor.event_handlers.sync_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should not run")),
    )
    result = ingest_webhook_payload(webhook_event.payload)

    refreshed = WebhookEvent.objects.get(pk=webhook_event.pk)
    assert result.webhook_event.pk == webhook_event.pk
    assert refreshed.processing_attempts == 1


@pytest.mark.django_db
def test_stale_pending_delivery_is_reacquired(monkeypatch):
    webhook_event = WebhookEvent.objects.create(
        dedupe_key="event:global:evt_stale_pending",
        dedupe_scope="global",
        event_id="evt_stale_pending",
        event_type="product.updated",
        resource_name="products",
        processing_state=WebhookEvent.ProcessingState.PENDING,
        processing_attempts=1,
        processed_at=timezone.now() - (PENDING_WEBHOOK_LEASE + timedelta(minutes=1)),
        payload={
            "event_id": "evt_stale_pending",
            "event_type": "product.updated",
            "data": {"id": "pro_stale_pending"},
        },
    )

    seen = {}

    def fake_sync_payload(*args, **kwargs):
        seen["called"] = True
        return SimpleNamespace(paddle_id="pro_stale_pending")

    monkeypatch.setattr("django_paddle_mor.event_handlers.sync_payload", fake_sync_payload)
    result = ingest_webhook_payload(webhook_event.payload)

    refreshed = WebhookEvent.objects.get(pk=webhook_event.pk)
    assert seen["called"] is True
    assert refreshed.processing_attempts == 2
    assert result.webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED


@pytest.mark.django_db
def test_legacy_global_dedupe_keys_are_migrated_in_place():
    legacy_event = WebhookEvent.objects.create(
        dedupe_key="event:evt_legacy",
        event_id="evt_legacy",
        event_type="product.updated",
        resource_name="products",
        processing_state=WebhookEvent.ProcessingState.FAILED,
        payload={
            "event_id": "evt_legacy",
            "event_type": "product.updated",
            "data": {"id": "pro_legacy"},
        },
    )

    replay_result = ingest_webhook_payload(legacy_event.payload, force_process=True)

    assert WebhookEvent.objects.filter(event_id="evt_legacy").count() == 1
    assert replay_result.webhook_event.dedupe_key == "event:global:evt_legacy"


@pytest.mark.django_db
def test_pre_process_signal_exception_marks_event_failed():
    def raising_receiver(sender, **kwargs):
        raise RuntimeError("pre-process receiver failed")

    webhook_pre_process.connect(raising_receiver)
    try:
        result = ingest_webhook_payload(
            {
                "event_id": "evt_pre_process_failure",
                "event_type": "product.updated",
                "data": {"id": "pro_pre_process_failure"},
            }
        )
    finally:
        webhook_pre_process.disconnect(raising_receiver)

    webhook_event = WebhookEvent.objects.get(event_id="evt_pre_process_failure")
    assert result.sync_error == "pre-process receiver failed"
    assert webhook_event.processing_state == WebhookEvent.ProcessingState.FAILED


@pytest.mark.django_db
def test_webhook_lifecycle_signals_fire_for_successful_processing(client, monkeypatch):
    recorded = []

    def pre_validate(sender, **kwargs):
        recorded.append(("pre_validate", kwargs["endpoint"]))

    def post_validate(sender, **kwargs):
        recorded.append(("post_validate", kwargs["valid"]))

    def pre_process(sender, **kwargs):
        recorded.append(("pre_process", kwargs["webhook_event"].event_id))

    def post_process(sender, **kwargs):
        recorded.append(("post_process", kwargs["success"]))

    webhook_pre_validate.connect(pre_validate)
    webhook_post_validate.connect(post_validate)
    webhook_pre_process.connect(pre_process)
    webhook_post_process.connect(post_process)

    try:
        monkeypatch.setattr(
            "django_paddle_mor.views.PaddleAPI.verify_webhook",
            lambda self, request, **kwargs: True,
        )

        response = client.post(
            reverse("django_paddle_mor:paddle_webhook"),
            data='{"event_id":"evt_signal","event_type":"product.updated","data":{"id":"pro_signal"}}',
            content_type="application/json",
        )
    finally:
        webhook_pre_validate.disconnect(pre_validate)
        webhook_post_validate.disconnect(post_validate)
        webhook_pre_process.disconnect(pre_process)
        webhook_post_process.disconnect(post_process)

    assert response.status_code == 200
    assert recorded == [
        ("pre_validate", None),
        ("post_validate", True),
        ("pre_process", "evt_signal"),
        ("post_process", True),
    ]


@pytest.mark.django_db
def test_webhook_processing_error_signal_and_failure_state(monkeypatch):
    recorded = []

    def processing_error(sender, **kwargs):
        recorded.append(str(kwargs["exception"]))

    webhook_processing_error.connect(processing_error)
    monkeypatch.setattr(
        "django_paddle_mor.event_handlers.sync_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("temporary sync failure")),
    )

    try:
        result = ingest_webhook_payload(
            {
                "event_id": "evt_failure_signal",
                "event_type": "product.updated",
                "data": {"id": "pro_failure"},
            }
        )
    finally:
        webhook_processing_error.disconnect(processing_error)

    webhook_event = WebhookEvent.objects.get(event_id="evt_failure_signal")
    assert result.sync_error == "temporary sync failure"
    assert webhook_event.processing_state == WebhookEvent.ProcessingState.FAILED
    assert webhook_event.processing_attempts == 1
    assert recorded == ["temporary sync failure"]


@pytest.mark.django_db
def test_reprocess_paddle_webhooks_command_retries_failed_events(monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.event_handlers.sync_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("temporary sync failure")),
    )
    ingest_webhook_payload(
        {
            "event_id": "evt_reprocess",
            "event_type": "product.updated",
            "data": {"id": "pro_reprocess"},
        }
    )

    monkeypatch.setattr(
        "django_paddle_mor.event_handlers.sync_payload",
        lambda *args, **kwargs: SimpleNamespace(paddle_id="pro_reprocess"),
    )
    stdout = StringIO()
    call_command("reprocess_paddle_webhooks", stdout=stdout)

    webhook_event = WebhookEvent.objects.get(event_id="evt_reprocess")
    assert webhook_event.processing_state == WebhookEvent.ProcessingState.PROCESSED
    assert webhook_event.processing_attempts == 2
    assert webhook_event.sync_error == ""
    assert "evt_reprocess: processed" in stdout.getvalue()


@pytest.mark.django_db
def test_reprocess_paddle_webhooks_command_skips_fresh_pending_events():
    WebhookEvent.objects.create(
        dedupe_key="event:global:evt_fresh_pending",
        dedupe_scope="global",
        event_id="evt_fresh_pending",
        event_type="product.updated",
        resource_name="products",
        processing_state=WebhookEvent.ProcessingState.PENDING,
        processing_attempts=1,
        processed_at=timezone.now(),
        payload={
            "event_id": "evt_fresh_pending",
            "event_type": "product.updated",
            "data": {"id": "pro_fresh_pending"},
        },
    )

    stdout = StringIO()
    call_command("reprocess_paddle_webhooks", stdout=stdout)

    assert "No webhook events matched the selection." in stdout.getvalue()


@pytest.mark.django_db
def test_reprocessing_deleted_endpoint_event_reuses_original_dedupe_scope():
    endpoint = WebhookEndpoint.objects.create(label="Replay endpoint", secret="whsec_replay")
    ingest_webhook_payload(
        {
            "event_id": "evt_endpoint_replay",
            "event_type": "product.updated",
            "data": {"id": "pro_endpoint_replay"},
        },
        endpoint=endpoint,
    )
    webhook_event = WebhookEvent.objects.get(event_id="evt_endpoint_replay")

    endpoint.delete()
    replay_result = ingest_webhook_payload(
        webhook_event.payload,
        headers=webhook_event.headers,
        signature_verified=webhook_event.signature_verified,
        dedupe_scope=webhook_event.dedupe_scope,
        force_process=True,
    )

    assert WebhookEvent.objects.filter(event_id="evt_endpoint_replay").count() == 1
    assert replay_result.webhook_event.dedupe_scope == webhook_event.dedupe_scope
