"""Live API tests (iteration 53) for Retailer Doc Points 11 & 12.

Modules covered:
- routes/staff.py :: admin_test_retailer_otp  (POST /api/admin/staff/retailer/test-otp)
- routes/staff.py :: admin_incentive_report   (GET  /api/admin/staff/incentives/report)
- routes/staff.py :: admin_incentive_report_csv (GET /api/admin/staff/incentives/report.csv)
- server.py :: send_otp_whatsapp DLT wording
"""
import csv
import io
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

CREDS_FILE = Path("/app/memory/test_credentials.md")


@pytest.fixture(scope="session")
def admin_credentials():
    if not CREDS_FILE.exists():
        pytest.skip("missing test_credentials.md")
    content = CREDS_FILE.read_text(encoding="utf-8")
    block = content.split("## Admin Dashboard")[1]
    u = re.search(r"Username:\s*`([^`]+)`", block)
    p = re.search(r"Password:\s*`([^`]+)`", block)
    if not u or not p:
        pytest.skip("admin creds not parseable")
    return {"username": u.group(1), "password": p.group(1)}


@pytest.fixture(scope="session")
def admin_client(admin_credentials):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/admin/login", json=admin_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in login response: {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------------- Point 11: OTP wording + test-otp diagnostic ----------------

def test_point11_dlt_template_wording():
    src = Path("/app/backend/server.py").read_text(encoding="utf-8")
    assert 'text = f"Your verification OTP is {otp} Use this at CP67 Mall."' in src
    idx = src.index("async def send_otp_whatsapp")
    body = src[idx:idx + 1600]
    assert "Homeland Advantage" not in body
    assert "Valid for 5 minutes" not in body


def test_point11_test_otp_requires_auth():
    r = requests.post(f"{BASE_URL}/api/admin/staff/retailer/test-otp",
                      json={"phone": "9999999999"}, timeout=30)
    assert r.status_code in (401, 403), r.text[:200]


def test_point11_test_otp_non_whitelisted(admin_client):
    r = admin_client.post(f"{BASE_URL}/api/admin/staff/retailer/test-otp",
                          json={"phone": "9000000019"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["success"] is False
    assert "whitelisted retailer manager" in data["message"]


def test_point11_test_otp_bad_phone(admin_client):
    r = admin_client.post(f"{BASE_URL}/api/admin/staff/retailer/test-otp",
                          json={"phone": "12345"}, timeout=30)
    assert r.status_code == 400, r.text[:300]


def test_point11_test_otp_whitelisted_manager(admin_client):
    phone = "9" + uuid.uuid4().int.__str__()[:9]
    create = admin_client.post(f"{BASE_URL}/api/admin/staff/retailer-managers", json={
        "name": "TEST_QA Manager", "phone": phone, "brands": ["Nike"], "is_active": True,
    }, timeout=30)
    assert create.status_code in (200, 201), create.text[:300]
    mgr_id = (create.json().get("manager") or create.json()).get("id")
    try:
        r = admin_client.post(f"{BASE_URL}/api/admin/staff/retailer/test-otp",
                              json={"phone": phone}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "delivery" in data, data
        d = data["delivery"]
        assert set(["whatsapp", "sms"]).issubset(d.keys()), d
        # per-channel diagnostics must be dicts with status info
        for ch in ("whatsapp", "sms"):
            assert d[ch] is None or isinstance(d[ch], dict), d
        assert data.get("manager_name") == "TEST_QA Manager"
        print(f"delivery diagnostics: {d}")
        assert data["success"] is True, f"OTP delivery failed: {d}"
    finally:
        if mgr_id:
            admin_client.delete(f"{BASE_URL}/api/admin/staff/retailer-managers/{mgr_id}", timeout=30)


# ---------------- Point 12: incentive report ----------------

REG_FIELDS = ["id", "type", "status", "amount", "customer_phone", "staff_code",
              "staff_name", "staff_phone", "staff_brand", "staff_brand_category",
              "created_at", "approved_at"]


def test_point12_report_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", timeout=30)
    assert r.status_code in (401, 403)


def test_point12_report_registration(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                         params={"incentive_type": "registration"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "rows" in data and "summary" in data
    s = data["summary"]
    for k in ("registration_count", "bill_upload_count", "total_amount", "redeemable_amount", "total"):
        assert k in s, s
    assert s["bill_upload_count"] == 0
    assert s["registration_count"] == len(data["rows"])
    if data["rows"]:
        row = data["rows"][0]
        missing = [f for f in REG_FIELDS if f not in row]
        assert not missing, f"missing fields {missing} in {row}"
        assert row["type"] == "registration"
        assert "_id" not in row
    else:
        pytest.skip("no registration incentives seeded")


def test_point12_report_bill_upload(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                         params={"incentive_type": "bill_upload"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["summary"]["registration_count"] == 0
    if not data["rows"]:
        pytest.skip("no bill_upload incentives seeded")
    row = data["rows"][0]
    for f in REG_FIELDS + ["bill_id", "bill_value"]:
        assert f in row, f"missing {f} in {row}"
    assert row["type"] == "bill_upload"


def test_point12_report_all_types(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report", timeout=60)
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["total"] == len(r.json()["rows"])
    assert s["registration_count"] + s["bill_upload_count"] <= s["total"]


def test_point12_report_status_filter(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                         params={"status": "redeemable"}, timeout=60)
    assert r.status_code == 200
    assert all(x["status"] == "redeemable" for x in r.json()["rows"])


def test_point12_report_date_filter_narrows(admin_client):
    allr = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report", timeout=60).json()
    narrow = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                              params={"start_date": "1999-01-01", "end_date": "1999-01-02"},
                              timeout=60)
    assert narrow.status_code == 200
    assert narrow.json()["summary"]["total"] == 0
    assert narrow.json()["summary"]["total"] <= allr["summary"]["total"]


def test_point12_report_brand_filter(admin_client):
    allr = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report", timeout=60).json()
    brands = [x.get("staff_brand") for x in allr["rows"] if x.get("staff_brand")]
    if not brands:
        pytest.skip("no branded incentive rows")
    brand = brands[0]
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                         params={"brand": brand}, timeout=60)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows, "brand filter returned nothing for an existing brand"
    assert all((x["staff_brand"] or "").lower() == brand.lower() for x in rows)
    assert len(rows) <= allr["summary"]["total"]


def test_point12_report_staff_id_filter(admin_client):
    allr = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report", timeout=60).json()
    sids = [x.get("staff_id") for x in allr["rows"] if x.get("staff_id")]
    if not sids:
        pytest.skip("no incentive rows with staff_id")
    sid = sids[0]
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report",
                         params={"staff_id": sid}, timeout=60)
    assert r.status_code == 200
    assert all(x["staff_id"] == sid for x in r.json()["rows"])


EXPECTED_CSV_HEADER = ["Type", "Staff Code", "Staff Name", "Staff Phone", "Brand", "Category",
                       "Store", "Customer Phone", "Amount", "Status", "Bill No", "Bill Store",
                       "Bill Amount", "Bill Status", "Created At", "Approved At"]


def test_point12_report_csv(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report.csv",
                         params={"incentive_type": "bill_upload"}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows, "empty CSV"
    assert rows[0] == EXPECTED_CSV_HEADER, rows[0]
    for row in rows[1:]:
        assert row[0] == "bill_upload"


def test_point12_report_csv_registration(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/admin/staff/incentives/report.csv",
                         params={"incentive_type": "registration"}, timeout=90)
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == EXPECTED_CSV_HEADER
    # Customer Phone column (index 7) must be populated for registration rows
    if len(rows) > 1:
        assert any(row[7] for row in rows[1:]), "no customer phone in registration CSV"


# ---------------- Point 13/14: second bill without a new scan gets no credit ----------------

def test_point14_second_bill_without_new_scan_gets_no_credit():
    """Point 13/14: one scan = one bill decision. After the first bill consumes the
    attribution, a second (brand-matching) bill must NOT credit the retailer."""
    import asyncio
    import sys
    from datetime import datetime, timezone
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    from routes.staff import create_or_activate_bill_incentive, bind_db

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        bind_db(db)
        sid = f"TEST_staff_{uuid.uuid4().hex[:8]}"
        code = f"HL-SEQ{uuid.uuid4().hex[:4].upper()}"
        cust = "98" + uuid.uuid4().int.__str__()[:8]
        b1 = f"TEST_bill_{uuid.uuid4().hex[:8]}"
        b2 = f"TEST_bill_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            await db.retail_staff.insert_one({
                "id": sid, "staff_code": code, "name": "TEST_Seq Staff", "phone": "9700000053",
                "brand_name": "Nike", "is_active": True, "created_at": now})
            await db.staff_attributions.insert_one({
                "id": str(uuid.uuid4()), "customer_phone": cust, "staff_id": sid,
                "staff_code": code, "created_at": now,
                "expires_at": "2099-01-01T00:00:00+00:00", "used": False})
            for b in (b1, b2):
                await db.bills.insert_one({"id": b, "user_phone": cust, "amount": 1000,
                                           "store_name": "Nike", "status": "auto_approved",
                                           "created_at": now})
            await create_or_activate_bill_incentive(b1, cust, "auto_approved", bill_value=1000.0)
            await create_or_activate_bill_incentive(b2, cust, "auto_approved", bill_value=1000.0)

            assert await db.staff_incentives.find_one({"bill_id": b1}) is not None, "first bill should credit"
            assert await db.staff_incentives.find_one({"bill_id": b2}) is None, \
                "second bill without a new QR scan must NOT credit the retailer"
        finally:
            await db.retail_staff.delete_many({"id": sid})
            await db.staff_attributions.delete_many({"customer_phone": cust})
            await db.staff_incentives.delete_many({"customer_phone": cust})
            await db.bills.delete_many({"id": {"$in": [b1, b2]}})

    asyncio.run(run())
