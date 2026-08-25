"""Iteration 54 — Hardening verification for the two endpoints that returned
raw HTTP 500 on production:
  • GET  /api/bills/{bill_id}/image
  • POST /api/admin/bills/{bill_id}/edit-brand

Critical assertion: neither endpoint may ever return a raw/empty HTTP 500.
Validation errors must be 4xx with a JSON `detail`.
"""
import base64
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or backend_env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or backend_env.get("DB_NAME")


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text()
    m = re.search(r"## Admin Dashboard\s*\n- Username: `([^`]+)`\s*\n- Password: `([^`]+)`", c)
    if not m:
        pytest.skip("admin creds not found in test_credentials.md")
    return {"username": m.group(1), "password": m.group(2)}


@pytest.fixture(scope="session")
def token(creds):
    r = requests.post(f"{BASE_URL}/api/admin/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo():
    cl = MongoClient(MONGO_URL)
    yield cl[DB_NAME]
    cl.close()


@pytest.fixture(scope="session")
def seeded_bills(mongo):
    """Seed 4 bill shapes we need to exercise the image endpoint."""
    # 1x1 png repeated to exceed the 200-byte placeholder guard
    png = base64.b64encode(os.urandom(400)).decode()
    ids = {}
    docs = []

    def mk(key, image_url):
        bid = f"TEST-I54-{key}-{uuid.uuid4().hex[:6]}"
        ids[key] = bid
        d = {
            "id": bid,
            "user_id": "TEST-I54-user",
            "store_name": "TestBrandOriginal",
            "bill_no": f"T54{uuid.uuid4().hex[:5]}",
            "amount": 1000.0,
            "status": "manual_review",
            "image_hash": f"hash-{key}",
        }
        if image_url is not None:
            d["image_url"] = image_url
        docs.append(d)

    mk("valid", f"data:image/png;base64,{png}")
    mk("corrupt", "data:image/jpeg;base64,AAAA")           # <200 bytes placeholder
    mk("empty", "")                                         # empty string
    mk("missing", None)                                     # field absent entirely
    mk("weird", "ftp://nowhere/x.jpg")                      # unrecognised format
    mk("editable", f"data:image/png;base64,{png}")          # for edit-brand
    mk("editable2", f"data:image/png;base64,{png}")         # for edit-brand reprocess

    mongo.bills.insert_many(docs)
    yield ids
    mongo.bills.delete_many({"id": {"$in": list(ids.values())}})


def assert_not_raw_500(r, label):
    assert r.status_code != 500 or r.text.strip().startswith("{"), \
        f"{label}: raw/empty HTTP 500 (body={r.text[:200]!r})"


# ================= GET /api/bills/{id}/image =================
class TestBillImage:
    def test_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/bills/anything/image", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_valid_data_image(self, client, seeded_bills):
        r = client.get(f"{BASE_URL}/api/bills/{seeded_bills['valid']}/image", timeout=60)
        assert_not_raw_500(r, "valid image")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["image_url"].startswith("data:image/png;base64,")
        assert d["image_hash"] == "hash-valid"
        assert d["fetch_error"] is None

    def test_corrupted_placeholder_image(self, client, seeded_bills):
        r = client.get(f"{BASE_URL}/api/bills/{seeded_bills['corrupt']}/image", timeout=60)
        assert_not_raw_500(r, "corrupt image")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["image_url"] is None
        assert "placeholder" in (d["fetch_error"] or "").lower()

    @pytest.mark.parametrize("key", ["empty", "missing"])
    def test_no_image_on_record(self, client, seeded_bills, key):
        r = client.get(f"{BASE_URL}/api/bills/{seeded_bills[key]}/image", timeout=60)
        assert_not_raw_500(r, f"{key} image")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["image_url"] is None
        assert d["fetch_error"] == "No image on record for this bill."

    def test_unrecognised_format(self, client, seeded_bills):
        r = client.get(f"{BASE_URL}/api/bills/{seeded_bills['weird']}/image", timeout=60)
        assert_not_raw_500(r, "weird image")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["image_url"] is None
        assert d["fetch_error"] == "Unrecognised image format on record."

    def test_unknown_bill_404(self, client):
        r = client.get(f"{BASE_URL}/api/bills/NO-SUCH-BILL-54/image", timeout=30)
        assert_not_raw_500(r, "unknown bill")
        assert r.status_code == 404, r.text[:300]
        assert r.json().get("detail") == "Bill not found"

    def test_existing_sample_bill_no_500(self, client, mongo):
        """Regression on the real production-like row referenced by the user."""
        doc = mongo.bills.find_one({"id": "TEST-1c0d66220b"})
        if not doc:
            pytest.skip("sample bill TEST-1c0d66220b not present")
        r = client.get(f"{BASE_URL}/api/bills/TEST-1c0d66220b/image", timeout=60)
        assert_not_raw_500(r, "sample bill")
        assert r.status_code == 200, r.text[:300]
        assert set(["image_url", "image_hash", "fetch_error"]).issubset(r.json().keys())


# ============ POST /api/admin/bills/{id}/edit-brand ============
class TestEditBrand:
    def test_auth_required(self):
        r = requests.post(f"{BASE_URL}/api/admin/bills/x/edit-brand",
                          json={"new_store_name": "Z"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_edit_no_reprocess_persists(self, client, seeded_bills, mongo):
        bid = seeded_bills["editable"]
        r = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                        json={"new_store_name": "TEST_Adidas Corrected", "reprocess": False},
                        timeout=60)
        assert_not_raw_500(r, "edit-brand reprocess=false")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["success"] is True
        assert d["reprocessed"] is False
        assert d["store_name"] == "TEST_Adidas Corrected"
        # persistence check
        doc = mongo.bills.find_one({"id": bid}, {"_id": 0})
        assert doc["store_name"] == "TEST_Adidas Corrected"
        assert doc.get("brand_edited_by")
        assert "TestBrandOriginal" in (doc.get("admin_notes") or "")

    def test_edit_reprocess_queued_returns_immediately(self, client, seeded_bills, mongo):
        import time
        bid = seeded_bills["editable2"]
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/admin/bills/{bid}/edit-brand",
                        json={"new_store_name": "TEST_Zara Corrected", "reprocess": True},
                        timeout=90)
        elapsed = time.time() - t0
        assert_not_raw_500(r, "edit-brand reprocess=true")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["reprocessed"] == "queued", d
        assert d["success"] is True
        assert "background" in (d.get("message") or "").lower()
        assert elapsed < 20, f"queued mode blocked for {elapsed:.1f}s (should return immediately)"
        doc = mongo.bills.find_one({"id": bid}, {"_id": 0})
        assert doc["store_name"] == "TEST_Zara Corrected"

    def test_unknown_bill_404(self, client):
        r = client.post(f"{BASE_URL}/api/admin/bills/NO-SUCH-BILL-54/edit-brand",
                        json={"new_store_name": "X", "reprocess": False}, timeout=30)
        assert_not_raw_500(r, "edit-brand unknown")
        assert r.status_code == 404, r.text[:300]
        assert r.json().get("detail") == "Bill not found"

    def test_empty_name_400(self, client, seeded_bills):
        r = client.post(f"{BASE_URL}/api/admin/bills/{seeded_bills['valid']}/edit-brand",
                        json={"new_store_name": "   ", "reprocess": False}, timeout=30)
        assert_not_raw_500(r, "edit-brand empty name")
        assert r.status_code == 400, r.text[:300]
        assert "required" in r.json().get("detail", "").lower()

    def test_missing_field_422(self, client, seeded_bills):
        r = client.post(f"{BASE_URL}/api/admin/bills/{seeded_bills['valid']}/edit-brand",
                        json={"reprocess": False}, timeout=30)
        assert_not_raw_500(r, "edit-brand missing field")
        assert r.status_code == 422, r.text[:300]
        assert "detail" in r.json()

    def test_wrong_type_payload_no_500(self, client, seeded_bills):
        r = client.post(f"{BASE_URL}/api/admin/bills/{seeded_bills['valid']}/edit-brand",
                        json={"new_store_name": {"a": 1}, "reprocess": "notabool"}, timeout=30)
        assert_not_raw_500(r, "edit-brand wrong types")
        assert r.status_code == 422, r.text[:300]
