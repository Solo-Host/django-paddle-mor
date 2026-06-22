from __future__ import annotations

import json

from django.db import transaction
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from .client import PaddleAPI
from .event_handlers import ingest_webhook_payload
from .exceptions import WebhookVerificationError
from .models import WebhookEndpoint
from .signals import webhook_post_validate, webhook_pre_validate


@transaction.non_atomic_requests
@csrf_exempt
def paddle_webhook(request: HttpRequest, endpoint_uuid=None):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    endpoint = None
    if endpoint_uuid is not None:
        endpoint = get_object_or_404(WebhookEndpoint, uuid=endpoint_uuid, enabled=True)

    paddle_api = PaddleAPI()
    webhook_pre_validate.send_robust(sender=paddle_webhook, request=request, endpoint=endpoint)
    try:
        if endpoint is not None:
            signature_verified = paddle_api.verify_webhook(
                request,
                secrets=endpoint.verification_secrets() or None,
            )
        else:
            signature_verified = paddle_api.verify_webhook(request)
    except WebhookVerificationError as exc:
        return JsonResponse({"detail": str(exc)}, status=500)

    webhook_post_validate.send_robust(
        sender=paddle_webhook,
        request=request,
        endpoint=endpoint,
        valid=signature_verified,
    )

    if not signature_verified:
        return JsonResponse({"detail": "Invalid Paddle signature."}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Webhook payload must be a JSON object."}, status=400)

    try:
        ingestion_result = ingest_webhook_payload(
            payload,
            headers=dict(request.headers.items()),
            signature_verified=True,
            endpoint=endpoint,
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse(
        {
            "endpoint_uuid": str(endpoint.uuid) if endpoint else None,
            "event_id": ingestion_result.webhook_event.event_id,
            "event_type": ingestion_result.webhook_event.event_type,
            "resource_name": ingestion_result.webhook_event.resource_name,
            "synced_object_id": getattr(ingestion_result.synced_resource, "paddle_id", None),
            "processing_state": ingestion_result.webhook_event.processing_state,
            "processing_attempts": ingestion_result.webhook_event.processing_attempts,
            "sync_error": ingestion_result.sync_error or None,
        },
        status=500 if ingestion_result.sync_error else 200,
    )
