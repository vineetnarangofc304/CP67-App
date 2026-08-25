"""Emergent Object Storage client — used to move multi-MB bill image payloads
out of the Mongo `bills` document into blob storage. See PRD.md session 19/20.

The bill.image_url field can now carry these prefixes:
  - data:image/*;base64,<payload>   (legacy inline)
  - base64:<payload>                 (legacy inline)
  - https://...                      (Karix media, ephemeral)
  - objstore:<path>                  (NEW — stored in Emergent Object Storage)

Reads normalise `objstore:` back to a data: URL in the /image endpoint.

Async variants (aput_object / aget_object / aupload_bill_image /
aresolve_objstore_url) MUST be used from inside FastAPI async handlers so
the blocking `requests` calls don't stall the event loop. Sync variants
are kept for one-off scripts or tests.
"""
from __future__ import annotations

import asyncio
import os
import logging
import threading
from pathlib import Path
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

# Session-20 hardening: load .env explicitly so this module works even when
# imported before server.py (e.g. from a background job or a unit test).
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)


def _base_url() -> str:
    base = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
    return base.rstrip("/") + "/objstore/api/v1/storage"


def _emergent_key() -> Optional[str]:
    return os.environ.get("EMERGENT_LLM_KEY")


APP_NAME = "cp67-mall"

_storage_key: Optional[str] = None
_init_lock = threading.Lock()


def init_storage() -> Optional[str]:
    """Idempotent init. Returns storage_key or None if init fails.
    Callers must handle None — object-storage is a mitigation, not a hard
    dependency; if init fails we fall back to inline storage."""
    global _storage_key
    if _storage_key:
        return _storage_key
    with _init_lock:
        if _storage_key:
            return _storage_key
        key = _emergent_key()
        if not key:
            logger.warning("storage.init_storage: EMERGENT_LLM_KEY missing (env not loaded)")
            return None
        try:
            resp = requests.post(
                f"{_base_url()}/init",
                json={"emergent_key": key},
                timeout=30,
            )
            resp.raise_for_status()
            _storage_key = resp.json().get("storage_key")
            if _storage_key:
                logger.info("Object storage initialised")
            return _storage_key
        except Exception as e:
            logger.error(f"storage.init_storage failed: {e}")
            return None


def put_object(path: str, data: bytes, content_type: str) -> Optional[dict]:
    """Upload bytes. Returns {'path','size','etag'} or None on failure."""
    key = init_storage()
    if not key:
        return None
    try:
        resp = requests.put(
            f"{_base_url()}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"storage.put_object failed for {path}: {e}")
        return None


def get_object(path: str) -> Optional[Tuple[bytes, str]]:
    """Download. Returns (bytes, content_type) or None on failure."""
    key = init_storage()
    if not key:
        return None
    try:
        resp = requests.get(
            f"{_base_url()}/objects/{path}",
            headers={"X-Storage-Key": key},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    except Exception as e:
        logger.error(f"storage.get_object failed for {path}: {e}")
        return None


def upload_bill_image(bill_id: str, data: bytes, content_type: str = "image/jpeg") -> Optional[str]:
    """Convenience wrapper — uploads bill image and returns the `objstore:<path>`
    URL string ready to store in `bill.image_url`. Returns None on failure so
    callers can fall back to inline storage."""
    ext = "jpg"
    if content_type == "image/png":
        ext = "png"
    elif content_type == "image/webp":
        ext = "webp"
    elif content_type == "image/gif":
        ext = "gif"
    path = f"{APP_NAME}/bills/{bill_id}.{ext}"
    result = put_object(path, data, content_type)
    if not result:
        return None
    return f"objstore:{result.get('path', path)}"


def resolve_objstore_url(image_url: str) -> Optional[Tuple[bytes, str]]:
    """Parse `objstore:<path>` and download the underlying bytes.
    Returns (bytes, content_type) or None."""
    if not image_url or not image_url.startswith("objstore:"):
        return None
    path = image_url[len("objstore:"):]
    return get_object(path)


# ---------- Async wrappers ------------------------------------------------
# The blocking `requests` calls are pushed off the event loop with
# asyncio.to_thread so many simultaneous /image reads don't serialise
# behind each other.

async def aput_object(path: str, data: bytes, content_type: str) -> Optional[dict]:
    return await asyncio.to_thread(put_object, path, data, content_type)


async def aget_object(path: str) -> Optional[Tuple[bytes, str]]:
    return await asyncio.to_thread(get_object, path)


async def aupload_bill_image(bill_id: str, data: bytes, content_type: str = "image/jpeg") -> Optional[str]:
    return await asyncio.to_thread(upload_bill_image, bill_id, data, content_type)


async def aresolve_objstore_url(image_url: str) -> Optional[Tuple[bytes, str]]:
    return await asyncio.to_thread(resolve_objstore_url, image_url)
