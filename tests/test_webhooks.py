import pytest
from django.urls import reverse

from django_paddle_mor.event_handlers import ingest_webhook_payload
from django_paddle_mor.models import NotificationSetting, Product, WebhookEvent


@pytest.mark.django_db
def test_webhook_rejects_invalid_signatures(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: False,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data='{"event_id":"evt_123"}',
        content_type="application/json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_webhook_rejects_non_object_json_payloads(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data="[]",
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_webhook_rejects_invalid_utf8_payloads(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data=b"\xff",
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_webhook_rejects_non_string_occurred_at_values(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data='{"event_id":"evt_bad_ts","event_type":"product.updated","occurred_at":123,"data":{"id":"pro_123"}}',
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_webhook_ingests_payload_and_syncs_resource(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data="""
        {
          "event_id": "evt_123",
          "event_type": "product.updated",
          "occurred_at": "2026-01-01T00:00:00Z",
          "data": {
            "id": "pro_123",
            "name": "Growth",
            "status": "active"
          }
        }
        """,
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 200
    assert WebhookEvent.objects.filter(event_id="evt_123", event_type="product.updated").exists()
    assert Product.objects.filter(paddle_id="pro_123", name="Growth").exists()


@pytest.mark.django_db
def test_failed_resource_sync_still_persists_webhook_event():
    result = ingest_webhook_payload(
        {
            "event_id": "evt_bad",
            "event_type": "product.updated",
            "data": {
                "name": "Missing Product Id",
            },
        }
    )

    webhook_event = WebhookEvent.objects.get(event_id="evt_bad")
    assert result.sync_error
    assert "missing the 'id' field" in webhook_event.sync_error

@pytest.mark.django_db
def test_webhook_returns_500_when_sync_records_an_error(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data="""
        {
          "event_id": "evt_bad_http",
          "event_type": "product.updated",
          "data": {
            "name": "Missing Product Id"
          }
        }
        """,
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 500
    assert response.json()["sync_error"] is not None
    assert WebhookEvent.objects.filter(event_id="evt_bad_http").exists()


@pytest.mark.django_db
def test_webhook_with_older_top_level_timestamp_does_not_overwrite_newer_state():
    Product.sync_from_payload(
        {
            "id": "pro_older_guard",
            "name": "Newest Product State",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    )

    ingest_webhook_payload(
        {
            "event_id": "evt_older",
            "event_type": "product.updated",
            "occurred_at": "2026-01-01T00:00:00Z",
            "data": {
                "id": "pro_older_guard",
                "name": "Older via webhook",
            },
        }
    )

    product = Product.objects.get(paddle_id="pro_older_guard")
    assert product.name == "Newest Product State"


@pytest.mark.django_db
def test_notification_setting_secrets_are_redacted_before_persistence():
    ingest_webhook_payload(
        {
            "event_id": "evt_notification_setting",
            "event_type": "notification_setting.updated",
            "data": {
                "id": "ntfset_123",
                "name": "Primary endpoint",
                "endpoint_secret_key": "ntf_secret_value",
            },
        }
    )

    webhook_event = WebhookEvent.objects.get(event_id="evt_notification_setting")
    notification_setting = NotificationSetting.objects.get(paddle_id="ntfset_123")

    assert webhook_event.payload["data"]["endpoint_secret_key"] == "[REDACTED]"
    assert notification_setting.payload["endpoint_secret_key"] == "[REDACTED]"


@pytest.mark.django_db
def test_webhook_headers_are_filtered_before_persistence(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data='{"event_id":"evt_headers","event_type":"product.updated","data":{"id":"pro_hdr"}}',
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
        HTTP_AUTHORIZATION="Bearer secret-token",
        HTTP_COOKIE="sessionid=abc123",
        HTTP_USER_AGENT="Paddle-Test",
    )

    assert response.status_code == 200
    webhook_event = WebhookEvent.objects.get(event_id="evt_headers")
    assert webhook_event.headers["Paddle-Signature"] == "ts=1;h1=test"
    assert webhook_event.headers["User-Agent"] == "Paddle-Test"
    assert "Authorization" not in webhook_event.headers


@pytest.mark.django_db
def test_webhook_rejects_non_object_resource_data(client, monkeypatch):
    monkeypatch.setattr(
        "django_paddle_mor.views.PaddleAPI.verify_webhook",
        lambda self, request: True,
    )

    response = client.post(
        reverse("django_paddle_mor:paddle_webhook"),
        data='{"event_id":"evt_bad_data","event_type":"product.updated","data":[]}',
        content_type="application/json",
        HTTP_PADDLE_SIGNATURE="ts=1;h1=test",
    )

    assert response.status_code == 400
