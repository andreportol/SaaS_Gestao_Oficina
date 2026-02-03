from __future__ import annotations

import logging
from typing import Optional, Tuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _safe_key_info(api_key: str) -> Tuple[str, int]:
    cleaned = (api_key or "").strip()
    return cleaned[:6], len(cleaned)


def _parse_error_body(response: requests.Response) -> Tuple[Optional[str], object]:
    try:
        data = response.json()
    except Exception:
        return None, response.text

    if isinstance(data, dict):
        name = data.get("name")
        message = data.get("message") or data.get("error")
        if name and message:
            return f"{name}: {message}", data
        if message:
            return message, data
    return None, data


def send_email_resend(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: Optional[str] = None,
    from_email: Optional[str] = None,
    timeout: int = 20,
) -> Tuple[bool, Optional[str], Optional[int]]:
    api_key = (getattr(settings, "RESEND_API_KEY", "") or "").strip()
    email_from = (from_email or getattr(settings, "EMAIL_FROM", "") or "").strip()

    if not api_key or not email_from:
        logger.error("Resend config missing: RESEND_API_KEY or EMAIL_FROM not set.")
        return False, "RESEND_API_KEY ou EMAIL_FROM nao configurados.", None

    payload = {
        "from": email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    key_prefix, key_len = _safe_key_info(api_key)
    logger.info(
        "Resend send attempt | from=%s to=%s reply_to=%s subject=%s key_prefix=%s key_len=%s",
        email_from,
        to,
        reply_to or "-",
        subject,
        key_prefix,
        key_len,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(RESEND_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        logger.exception("Resend exception while sending email: %s", exc)
        return False, "Erro de comunicacao com o servico de email.", None

    if response.status_code >= 400:
        detail, body = _parse_error_body(response)
        logger.error(
            "Resend email failed | status=%s body=%s | from=%s to=%s reply_to=%s subject=%s key_prefix=%s key_len=%s",
            response.status_code,
            body,
            email_from,
            to,
            reply_to or "-",
            subject,
            key_prefix,
            key_len,
        )
        return False, detail or f"HTTP {response.status_code}", response.status_code

    logger.info("Resend email sent OK | status=%s", response.status_code)
    return True, None, response.status_code
