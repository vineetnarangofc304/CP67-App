"""Iteration 71 — Point 43: brand/banner image uploads move to Emergent Object Storage.

Covers:
  * POST /api/admin/brands/{id}/upload-image  -> 200, image_url = <BACKEND_PUBLIC_URL>/api/uploaded-image/brands/<id>_logo.jpg
    + DB logo_url/cover_image_url updated + store auto-sync + NO pod-local uploads/ file
  * POST /api/admin/banners/{id}/upload-image -> 200, /api/uploaded-image/banners/banner_<id>.jpg + DB image_url
  * GET  /api/uploaded-image/brands/<file>    -> 200 exact bytes + Cache-Control: public, max-age=86400
                                                404 unknown filename, 404 unknown category, 400 bad filename
  * error paths: 400 >5MB, 400 bad image_type, 502 when object storage init fails
"""
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest
import requests
from dotenv import dotenv_values
from fastapi import HTTPException

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _base.rstrip("/")
BACKEND_PUBLIC_URL = (dotenv_values("/app/backend/.env").get("BACKEND_PUBLIC_URL") or BASE_URL).rstrip("/")
# Origin (bypasses the preview ingress, which rewrites Cache-Control headers)
ORIGIN_URL = "http://localhost:8001"

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

CREDS_PATH = Path("/app/memory/test_credentials.md")
UPLOADS_DIR = Path("/app/backend/uploads")

try:
    _LOOP = asyncio.get_event_loop_policy().get_event_loop()
    if _LOOP.is_closed():
        raise RuntimeError
except RuntimeError:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _admin_creds():
    content = CREDS_PATH.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block).group(1)
    p = re.search(r"Password:\s*`([^`]+)`", block).group(1)
    return u, p


@pytest.fixture(scope="module")
def auth_headers():
    u, p = _admin_creds()
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": u, "password": p}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


# Minimal valid JPEG bytes (unique per run so cache can't mask a failure)
def _jpeg_bytes(marker: bytes):
    return b"\xff\xd8\xff\xe0" + marker + b"\x00" * 64 + b"\xff\xd9"


_created_brands = []
_created_banners = []


@pytest.fixture(scope="module")
def brand_id():
    bid = "TEST_ITER71_" + str(uuid.uuid4())[:8]
    _run(server.db.brands.insert_one({
        "id": bid,
        "brand_name": f"TEST_ITER71_Brand_{bid[-4:]}",
        "category": "Fashion",
        "description": "iteration71 objstore upload test",
        "is_active": True,
    }))
    _created_brands.append(bid)
    return bid


@pytest.fixture(scope="module")
def banner_id():
    bid = "TEST_ITER71_" + str(uuid.uuid4())[:8]
    _run(server.db.banners.insert_one({
        "id": bid, "title": "TEST_ITER71 Banner", "image_url": "", "position": 99, "is_active": False,
    }))
    _created_banners.append(bid)
    return bid


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for bid in _created_brands:
        _run(server.db.brands.delete_one({"id": bid}))
        _run(server.db.stores.delete_many({"name": {"$regex": "TEST_ITER71"}}))
    for bid in _created_banners:
        _run(server.db.banners.delete_one({"id": bid}))


class TestBrandUpload:
    """Point 43 — brand logo/cover upload to object storage."""

    def test_upload_brand_logo(self, auth_headers, brand_id):
        payload = _jpeg_bytes(b"BRANDLOGO71")
        before = set(p.name for p in UPLOADS_DIR.glob("*")) if UPLOADS_DIR.exists() else set()
        r = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=auth_headers,
            data={"image_type": "logo"},
            files={"file": ("logo.jpg", payload, "image/jpeg")},
            timeout=180,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["success"] is True
        assert body["field"] == "logo_url"
        expected = f"{BACKEND_PUBLIC_URL}/api/uploaded-image/brands/{brand_id}_logo.jpg"
        assert body["image_url"] == expected, body["image_url"]

        # DB updated
        doc = _run(server.db.brands.find_one({"id": brand_id}, {"_id": 0}))
        assert doc["logo_url"] == expected

        # store auto-sync fired
        store = _run(server.db.stores.find_one({"name": doc["brand_name"]}, {"_id": 0}))
        assert store is not None, "brand was not auto-synced to stores"
        assert store.get("logo_url") == expected

        # no pod-local file written
        after = set(p.name for p in UPLOADS_DIR.glob("*")) if UPLOADS_DIR.exists() else set()
        assert not any(brand_id in n for n in after - before), f"local file created: {after - before}"

        # served bytes match exactly
        g = requests.get(f"{BASE_URL}/api/uploaded-image/brands/{brand_id}_logo.jpg", timeout=120)
        assert g.status_code == 200, g.text[:300]
        assert g.content == payload
        assert "image" in g.headers.get("Content-Type", "")
        # NOTE: the preview ingress rewrites Cache-Control to "no-store, no-cache,
        # must-revalidate"; assert the app-level header against the origin.
        lg = requests.get(f"{ORIGIN_URL}/api/uploaded-image/brands/{brand_id}_logo.jpg", timeout=120)
        assert lg.status_code == 200
        assert lg.headers.get("Cache-Control") == "public, max-age=86400", lg.headers.get("Cache-Control")

    def test_upload_brand_cover(self, auth_headers, brand_id):
        payload = _jpeg_bytes(b"BRANDCOVER71")
        r = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=auth_headers,
            data={"image_type": "cover"},
            files={"file": ("cover.jpg", payload, "image/jpeg")},
            timeout=180,
        )
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        assert body["field"] == "cover_image_url"
        assert body["image_url"].endswith(f"/api/uploaded-image/brands/{brand_id}_cover.jpg")
        doc = _run(server.db.brands.find_one({"id": brand_id}, {"_id": 0}))
        assert doc["cover_image_url"] == body["image_url"]

    def test_bad_image_type(self, auth_headers, brand_id):
        r = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=auth_headers,
            data={"image_type": "banner"},
            files={"file": ("x.jpg", _jpeg_bytes(b"X"), "image/jpeg")},
            timeout=60,
        )
        assert r.status_code == 400, r.status_code
        assert "image_type" in r.json().get("detail", "")

    def test_too_large(self, auth_headers, brand_id):
        big = b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 100)
        r = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            headers=auth_headers,
            data={"image_type": "logo"},
            files={"file": ("big.jpg", big, "image/jpeg")},
            timeout=180,
        )
        assert r.status_code == 400, r.status_code
        assert "large" in r.json().get("detail", "").lower()

    def test_requires_auth(self, brand_id):
        r = requests.post(
            f"{BASE_URL}/api/admin/brands/{brand_id}/upload-image",
            data={"image_type": "logo"},
            files={"file": ("x.jpg", _jpeg_bytes(b"X"), "image/jpeg")},
            timeout=60,
        )
        assert r.status_code in (401, 403), r.status_code


class TestBannerUpload:
    """Point 43 — banner upload to object storage."""

    def test_upload_banner(self, auth_headers, banner_id):
        payload = _jpeg_bytes(b"BANNER71")
        before = set(p.name for p in UPLOADS_DIR.glob("*")) if UPLOADS_DIR.exists() else set()
        r = requests.post(
            f"{BASE_URL}/api/admin/banners/{banner_id}/upload-image",
            headers=auth_headers,
            files={"file": ("b.jpg", payload, "image/jpeg")},
            timeout=180,
        )
        assert r.status_code == 200, r.text[:400]
        expected = f"{BACKEND_PUBLIC_URL}/api/uploaded-image/banners/banner_{banner_id}.jpg"
        assert r.json()["image_url"] == expected, r.json()["image_url"]

        doc = _run(server.db.banners.find_one({"id": banner_id}, {"_id": 0}))
        assert doc["image_url"] == expected

        after = set(p.name for p in UPLOADS_DIR.glob("*")) if UPLOADS_DIR.exists() else set()
        assert not any(banner_id in n for n in after - before), f"local file created: {after - before}"

        g = requests.get(f"{BASE_URL}/api/uploaded-image/banners/banner_{banner_id}.jpg", timeout=120)
        assert g.status_code == 200, g.text[:300]
        assert g.content == payload
        lg = requests.get(f"{ORIGIN_URL}/api/uploaded-image/banners/banner_{banner_id}.jpg", timeout=120)
        assert lg.headers.get("Cache-Control") == "public, max-age=86400", lg.headers.get("Cache-Control")

    def test_banner_too_large(self, auth_headers, banner_id):
        big = b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 100)
        r = requests.post(
            f"{BASE_URL}/api/admin/banners/{banner_id}/upload-image",
            headers=auth_headers,
            files={"file": ("big.jpg", big, "image/jpeg")},
            timeout=180,
        )
        assert r.status_code == 400, r.status_code


class TestServeUploadedImage:
    """Point 43 — public GET /api/uploaded-image/{category}/{filename}."""

    def test_unknown_filename_404(self):
        r = requests.get(f"{BASE_URL}/api/uploaded-image/brands/TEST_ITER71_nope_logo.jpg", timeout=120)
        assert r.status_code == 404, r.status_code

    def test_unknown_category_404(self):
        r = requests.get(f"{BASE_URL}/api/uploaded-image/hacks/x.jpg", timeout=60)
        assert r.status_code == 404, r.status_code

    def test_traversal_filename_400(self):
        # ".." / leading "." in filename -> 400. URL-encoded "%2F" is normalised by the
        # proxy into a path with no route match (404) which is also safe.
        for bad in ("..secret.jpg", ".hidden.jpg"):
            r = requests.get(f"{BASE_URL}/api/uploaded-image/brands/{bad}", timeout=60)
            assert r.status_code == 400, f"{bad} -> {r.status_code}"

    def test_handler_rejects_slash_and_dotdot(self):
        for bad in ("a/b.jpg", "../secret.jpg", ".env"):
            with pytest.raises(HTTPException) as exc:
                _run(server.serve_uploaded_image("brands", bad))
            assert exc.value.status_code == 400, f"{bad} -> {exc.value.status_code}"

    def test_no_auth_required(self, auth_headers, brand_id):
        # public route: works without Authorization header (already covered above,
        # asserted here explicitly for the logo uploaded in TestBrandUpload)
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/uploaded-image/brands/{brand_id}_logo.jpg", timeout=120)
        assert r.status_code == 200


class TestObjectStorageFailure:
    """502 when object storage init/put fails."""

    def test_brand_upload_502(self, brand_id):
        import storage as storage_mod

        async def _fail(*a, **kw):
            return None

        class _F:
            filename = "x.jpg"

            async def read(self):
                return _jpeg_bytes(b"F")

        with mock.patch.object(storage_mod, "aput_object", _fail):
            with pytest.raises(HTTPException) as exc:
                _run(server.upload_brand_image(brand_id, "logo", _F(), {"username": "admin"}))
        assert exc.value.status_code == 502
        assert "storage" in exc.value.detail.lower()

    def test_banner_upload_502(self, banner_id):
        import storage as storage_mod

        async def _fail(*a, **kw):
            return None

        class _F:
            filename = "x.jpg"

            async def read(self):
                return _jpeg_bytes(b"F")

        with mock.patch.object(storage_mod, "aput_object", _fail):
            with pytest.raises(HTTPException) as exc:
                _run(server.upload_banner_image(banner_id, _F(), {"username": "admin"}))
        assert exc.value.status_code == 502
