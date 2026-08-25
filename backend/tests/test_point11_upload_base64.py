"""Point 11: /api/consumer/bills/upload-base64 tests + Point 11 multipart regression."""
import os
import io
import base64
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mall-engagement-hub.preview.emergentagent.com").rstrip("/")

# Small valid JPEG bytes (1x1 pixel)
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
    "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
    "1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100"
    "ffc4001f0000010501010101010100000000000000000102030405060708090a0bff"
    "c400b5100002010303020403050504040000017d01020300041105122131410613516107"
    "227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a"
    "3435363738393a434445464748494a535455565758595a636465666768696a737475"
    "767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4"
    "b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9ea"
    "f1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd0ffd9"
)


@pytest.fixture(scope="module")
def consumer_token():
    # Send OTP
    r1 = requests.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": "9876543210"})
    assert r1.status_code == 200, f"send-otp failed: {r1.status_code} {r1.text}"
    # Verify OTP
    r2 = requests.post(f"{BASE_URL}/api/consumer/auth/verify-otp", json={"phone": "9876543210", "otp": "1234"})
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    tok = r2.json().get("access_token") or r2.json().get("token")
    assert tok, f"no token in response: {r2.json()}"
    return tok


def auth_headers(tok):
    return {"Authorization": f"Bearer {tok}"}


def _unique_jpeg(salt: bytes = b"") -> bytes:
    # Append random bytes AFTER the JPEG EOI marker to ensure unique image_hash per test run
    return TINY_JPEG + salt + uuid.uuid4().bytes + str(time.time_ns()).encode()


def test_upload_base64_data_url(consumer_token):
    b64 = base64.b64encode(_unique_jpeg(b"a")).decode()
    data_url = f"data:image/jpeg;base64,{b64}"
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers={**auth_headers(consumer_token), "Content-Type": "application/json"},
        json={"image_base64": data_url},
    )
    assert r.status_code == 200, f"upload-base64 (data-url) failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("success") is True
    assert body.get("status") == "processing"
    assert body.get("bill_id")


def test_upload_base64_raw(consumer_token):
    raw_bytes = _unique_jpeg(b"b")
    b64 = base64.b64encode(raw_bytes).decode()
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers={**auth_headers(consumer_token), "Content-Type": "application/json"},
        json={"image_base64": b64},
    )
    assert r.status_code == 200, f"upload-base64 (raw) failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("success") is True
    assert body.get("bill_id")


def test_upload_base64_size_limit(consumer_token):
    # >10MB payload of decoded bytes → server rejects with 400
    big = b"\x00" * (10 * 1024 * 1024 + 100)
    b64 = base64.b64encode(big).decode()
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers={**auth_headers(consumer_token), "Content-Type": "application/json"},
        json={"image_base64": b64},
        timeout=60,
    )
    assert r.status_code == 400, f"expected 400 for oversize, got {r.status_code} {r.text[:200]}"
    assert "large" in r.text.lower() or "10mb" in r.text.lower()


def test_upload_base64_invalid_base64(consumer_token):
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers={**auth_headers(consumer_token), "Content-Type": "application/json"},
        json={"image_base64": "!!!not-base64!!!"},
    )
    # Either 400 (invalid base64) or 200 (lax decoder). Prefer 400.
    assert r.status_code in (400, 422), f"expected 400/422 for invalid base64, got {r.status_code}"


def test_multipart_upload_still_works(consumer_token):
    # Regression: /api/consumer/bills/upload (multipart) still works
    raw_bytes = _unique_jpeg(b"c")
    files = {"file": ("t.jpg", io.BytesIO(raw_bytes), "image/jpeg")}
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload",
        headers=auth_headers(consumer_token),
        files=files,
    )
    assert r.status_code == 200, f"multipart upload failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("success") is True
    assert body.get("bill_id")
