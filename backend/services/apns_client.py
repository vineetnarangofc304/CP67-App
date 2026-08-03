"""
Apple Push Notification service (APNs) — HTTP/2 sender for iOS builds.

Sends notifications to iPhones running the Homeland Advantage iOS app.

Configuration (add these to backend/.env):
    APNS_KEY_ID=XXXXXXXXXX             (10-char key ID from App Store Connect)
    APNS_TEAM_ID=YYYYYYYYYY            (10-char team ID from Apple Developer)
    APNS_BUNDLE_ID=com.fundle.cp67ios  (must match Xcode bundle ID)
    APNS_KEY_P8=/app/backend/keys/AuthKey_XXXXXXXXXX.p8   (path to your .p8 file)
    APNS_ENV=production                (or 'sandbox' for TestFlight)

How to obtain the .p8 key:
    1. https://appstoreconnect.apple.com → Users and Access → Keys → APNs
    2. + → give it a name → tick "Apple Push Notifications service (APNs)" → Continue → Register
    3. Download the .p8 file (you can only download ONCE — keep it safe)
    4. Note the Key ID (shown next to the key on the page)
    5. Team ID: top-right corner of https://developer.apple.com/account
"""

import os
import time
import json
import logging
from typing import Optional, List

import httpx
import jwt  # PyJWT is already installed

logger = logging.getLogger(__name__)

APNS_KEY_ID = os.environ.get("APNS_KEY_ID", "")
APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID", "")
APNS_BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID", "com.fundle.cp67ios")
APNS_KEY_PATH = os.environ.get("APNS_KEY_P8", "")
APNS_ENV = os.environ.get("APNS_ENV", "production")   # production | sandbox

_APNS_HOST = "api.push.apple.com" if APNS_ENV == "production" else "api.sandbox.push.apple.com"

# JWT token cache — Apple wants ONE JWT per key, refreshed every ~50 min
_jwt_cache = {"token": None, "issued_at": 0}


def _make_jwt() -> Optional[str]:
    """Sign a fresh APNs provider JWT. Cached for 50 minutes."""
    if not all([APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY_PATH]):
        return None
    now = int(time.time())
    if _jwt_cache["token"] and (now - _jwt_cache["issued_at"] < 50 * 60):
        return _jwt_cache["token"]
    try:
        with open(APNS_KEY_PATH, "r") as f:
            secret = f.read()
    except Exception as e:
        logger.error(f"APNs .p8 read failed: {e}")
        return None
    token = jwt.encode(
        {"iss": APNS_TEAM_ID, "iat": now},
        secret,
        algorithm="ES256",
        headers={"kid": APNS_KEY_ID},
    )
    _jwt_cache["token"] = token
    _jwt_cache["issued_at"] = now
    return token


def is_configured() -> bool:
    return bool(APNS_KEY_ID and APNS_TEAM_ID and APNS_KEY_PATH and os.path.exists(APNS_KEY_PATH))


async def send_apns(
    device_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
    badge: Optional[int] = None,
    sound: str = "default",
    thread_id: Optional[str] = None,
) -> dict:
    """Send a single push. Returns {'success': bool, 'status': int, 'body': str}."""
    if not is_configured():
        logger.warning("APNs not configured; skipping push")
        return {"success": False, "status": 0, "body": "not_configured"}

    provider_jwt = _make_jwt()
    if not provider_jwt:
        return {"success": False, "status": 0, "body": "jwt_failed"}

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": sound,
            "mutable-content": 1,
        }
    }
    if badge is not None:
        payload["aps"]["badge"] = badge
    if thread_id:
        payload["aps"]["thread-id"] = thread_id
    if data:
        payload.update(data)

    url = f"https://{_APNS_HOST}/3/device/{device_token}"
    headers = {
        "authorization": f"bearer {provider_jwt}",
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "content-type": "application/json",
    }

    try:
        # APNs requires HTTP/2 — httpx handles it via the h2 extra.
        # If h2 is not installed, httpx will attempt HTTP/1.1 and Apple will
        # respond 400. Ensure `pip install httpx[http2]` is done.
        async with httpx.AsyncClient(http2=True, timeout=10) as client:
            r = await client.post(url, headers=headers, content=json.dumps(payload))
        return {"success": r.status_code == 200, "status": r.status_code, "body": r.text}
    except Exception as e:
        logger.error(f"APNs send failed: {e}")
        return {"success": False, "status": 0, "body": str(e)}


async def send_apns_multi(device_tokens: List[str], title: str, body: str, **kw) -> dict:
    """Fan-out send. Returns aggregated stats."""
    sent, failed = 0, 0
    for tok in device_tokens:
        r = await send_apns(tok, title, body, **kw)
        if r.get("success"):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "total": len(device_tokens)}
