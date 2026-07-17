"""Iteration 29 — Batch tests for CP67 points 10-15."""
import os
import time
import base64
import io
import uuid
import requests
import pytest

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
CONSUMER_PHONE = "9876543210"
CONSUMER_OTP = "1234"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def consumer_token(s):
    # send-otp then verify with source=SRC_RWA
    s.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": CONSUMER_PHONE})
    r = s.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": CONSUMER_PHONE, "otp": CONSUMER_OTP, "source": "SRC_RWA"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def consumer_headers(consumer_token):
    return {"Authorization": f"Bearer {consumer_token}", "Content-Type": "application/json"}


# ---------- Point 15 — QR codes ----------
def test_p15_qr_links_include_rwa_and_office(admin_headers):
    r = requests.get(f"{BASE_URL}/api/qr-links", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("qr_codes") or data.get("links") or data if isinstance(data, list) else data.get("qr_codes", [])
    if isinstance(data, dict):
        items = data.get("qr_codes") or data.get("links") or []
    sources = [q.get("source_code") for q in items]
    assert "SRC_RWA" in sources, f"sources={sources}"
    assert "SRC_OFFICE" in sources, f"sources={sources}"


@pytest.mark.parametrize("qr_id", ["QR0124010", "QR0124011"])
def test_p15_qr_generate(admin_headers, qr_id):
    r = requests.get(f"{BASE_URL}/api/qr-codes/{qr_id}/generate", headers=admin_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    # Look for base64 image field
    img = j.get("image_base64") or j.get("qr_image") or j.get("image") or j.get("qr_code") or ""
    assert "base64" in img or len(img) > 100, f"no image in response: {j}"


# ---------- Point 15 — source capture ----------
def test_p15_first_touch_source_saved(admin_headers):
    """Register a brand-new phone with source=SRC_RWA and verify first_touch_source is captured."""
    # Use a random new phone to guarantee is_new=true
    import random
    new_phone = "9" + "".join(str(random.randint(0, 9)) for _ in range(9))
    ses = requests.Session()
    ses.post(f"{BASE_URL}/api/consumer/auth/send-otp", json={"phone": new_phone})
    r = ses.post(
        f"{BASE_URL}/api/consumer/auth/verify-otp",
        json={"phone": new_phone, "otp": CONSUMER_OTP, "source": "SRC_RWA"},
    )
    assert r.status_code == 200, r.text
    # Query users filtered by SRC_RWA source
    ur = requests.get(f"{BASE_URL}/api/users?source=SRC_RWA&limit=200", headers=admin_headers)
    assert ur.status_code == 200, ur.text
    data = ur.json()
    users = data if isinstance(data, list) else data.get("users", [])
    phones = [(u.get("phone") or "") for u in users]
    assert any(new_phone in p for p in phones), f"new phone {new_phone} not found in SRC_RWA users (n={len(users)})"
    # Cleanup — delete the test user
    try:
        for u in users:
            if new_phone in (u.get("phone") or ""):
                requests.delete(f"{BASE_URL}/api/users/{u['id']}", headers=admin_headers)
    except Exception:
        pass


# ---------- Point 13 — Nightly scheduler ----------
def test_p13_run_nightly_now(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/sync/nightly/run-now", headers=admin_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("success") is True
    assert "queued" in (j.get("message") or "").lower()


def test_p13_sync_jobs_list(admin_headers):
    # Give the queued job time to persist
    time.sleep(6)
    r = requests.get(f"{BASE_URL}/api/admin/sync/jobs", headers=admin_headers)
    assert r.status_code == 200, r.text
    jobs = r.json().get("jobs", [])
    assert isinstance(jobs, list)
    # Must have at least one nightly registration sync job
    kinds = [j.get("type") for j in jobs]
    assert "nightly_registration_sync" in kinds, f"types found: {kinds[:10]}"


# ---------- Point 14 — Legacy 154 sync ----------
def test_p14_legacy_154_sync_starts_and_progresses(admin_headers):
    r = requests.post(
        f"{BASE_URL}/api/admin/sync/legacy-154?include_bills=true", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("success") is True
    assert j.get("total") == 154
    job_id = j["job_id"]

    # Poll a few times
    processed = 0
    status = None
    for _ in range(10):
        time.sleep(3)
        pr = requests.get(f"{BASE_URL}/api/admin/sync/status/{job_id}", headers=admin_headers)
        assert pr.status_code == 200
        pj = pr.json()
        processed = pj.get("processed", 0)
        status = pj.get("status")
        for k in ("processed", "registered", "already", "failed", "bills_synced", "bills_failed"):
            assert k in pj, f"missing counter {k}: {pj}"
        if status == "completed":
            break
    assert processed > 0 or status == "completed", f"job made no progress: status={status} processed={processed}"


# ---------- Point 12 — WhatsApp auto force-credit toggle ----------
def test_p12_toggle_auto_force_credit(admin_headers, consumer_headers):
    # Save original
    orig = requests.get(f"{BASE_URL}/api/admin/app-settings", headers=admin_headers).json()
    orig_val = orig.get("auto_force_credit_on_fundle_reject", False)

    try:
        # Set true
        pr = requests.put(
            f"{BASE_URL}/api/admin/app-settings",
            headers=admin_headers,
            json={"auto_force_credit_on_fundle_reject": True},
        )
        assert pr.status_code == 200, pr.text

        # Verify via consumer endpoint
        cr = requests.get(f"{BASE_URL}/api/consumer/app-settings", headers=consumer_headers)
        assert cr.status_code == 200, cr.text
        body = cr.json()
        # response may be flat or wrapped in {'settings': {...}}
        settings = body.get("settings", body)
        assert settings.get("auto_force_credit_on_fundle_reject") is True
    finally:
        # Reset
        requests.put(
            f"{BASE_URL}/api/admin/app-settings",
            headers=admin_headers,
            json={"auto_force_credit_on_fundle_reject": orig_val},
        )


# ---------- Point 11 — JSON bill upload ----------
def _make_jpeg_bytes():
    try:
        from PIL import Image
        buf = io.BytesIO()
        img = Image.new("RGB", (80, 80), (200, 100, 50))
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception:
        # Fallback minimal JPEG (may not be valid image but should still be accepted as bytes)
        return bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
            "07090908"
        ) + os.urandom(200) + b"\xff\xd9"


def test_p11_upload_base64_with_data_prefix(consumer_headers):
    img_bytes = _make_jpeg_bytes() + os.urandom(500)
    b64 = base64.b64encode(img_bytes).decode()
    data_url = f"data:image/jpeg;base64,{b64}"
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers=consumer_headers,
        json={"image_base64": data_url},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("success") is True
    assert j.get("bill_id")
    assert j.get("status") in ("processing", "pending", "approved", "rejected")


def test_p11_upload_base64_raw(consumer_headers):
    img_bytes = _make_jpeg_bytes() + os.urandom(300)  # different hash
    b64 = base64.b64encode(img_bytes).decode()
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers=consumer_headers,
        json={"image_base64": b64},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("bill_id")


def test_p11_upload_base64_invalid(consumer_headers):
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload-base64",
        headers=consumer_headers,
        json={"image_base64": "!!!not-base64!!!"},
    )
    assert r.status_code == 400


# ---------- Point 10 — Bulk reprocess dry-run ----------
def test_p10_bulk_reprocess_dry_run(admin_headers):
    from datetime import datetime, timedelta, timezone
    to_d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_d = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    r = requests.post(
        f"{BASE_URL}/api/admin/bills/bulk-reprocess",
        headers=admin_headers,
        json={
            "from_date": from_d,
            "to_date": to_d,
            "force_credit_on_fundle_reject": True,
            "dry_run": True,
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # Expect candidate count
    assert ("candidates" in j) or ("count" in j) or ("total" in j) or ("bills" in j), f"unexpected: {j}"


# ---------- Regression ----------
def test_reg_admin_bills(admin_headers):
    r = requests.get(f"{BASE_URL}/api/bills?limit=5", headers=admin_headers)
    assert r.status_code == 200


def test_reg_admin_campaigns(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/campaigns", headers=admin_headers)
    assert r.status_code == 200


def test_reg_admin_app_settings_get(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/app-settings", headers=admin_headers)
    assert r.status_code == 200


def test_reg_consumer_campaigns_active(consumer_headers):
    r = requests.get(f"{BASE_URL}/api/consumer/campaigns/active", headers=consumer_headers)
    assert r.status_code == 200


def test_reg_multipart_upload_still_works(consumer_headers):
    """Legacy multipart upload endpoint."""
    img_bytes = _make_jpeg_bytes() + os.urandom(600)
    files = {"file": ("bill.jpg", img_bytes, "image/jpeg")}
    headers = {"Authorization": consumer_headers["Authorization"]}
    r = requests.post(
        f"{BASE_URL}/api/consumer/bills/upload", headers=headers, files=files
    )
    assert r.status_code == 200, r.text
    assert r.json().get("bill_id")
