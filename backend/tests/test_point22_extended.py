"""Point 22 extended regression: upload-bound attribution, rejection, registration
activation (14b), and alias-aware admin incentive report brand filter.
Throwaway Preview records only (prefix P22TEST, phone 7000022002) — cleaned up after each test."""
import os, sys, uuid, asyncio
from datetime import datetime, timezone, timedelta
import pytest
import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))
load_dotenv("/app/frontend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import routes.staff as staff_mod

TAG = "P22TEST"
PHONE = "7000022002"
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
COLLS = ("retail_staff", "staff_attributions", "staff_incentives", "staff_attribution_misses", "bills", "brands")


def _iso(dt):
    return dt.isoformat()


def _db():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    staff_mod._db = db
    return db


async def _cleanup(db):
    for c in COLLS:
        await db[c].delete_many({"$or": [{"tag": TAG}, {"customer_phone": PHONE}, {"user_phone": PHONE},
                                         {"staff_code": {"$regex": f"^{TAG}"}}, {"brand_name": {"$regex": f"^{TAG}"}}]})


async def _staff(db, brand="Dominos"):
    sid = f"{TAG}-{uuid.uuid4()}"
    await db.retail_staff.insert_one({"id": sid, "staff_code": f"{TAG}-S-{sid[-6:]}", "name": "P22", "phone": "7000022099",
                                      "brand_name": brand, "is_active": True,
                                      "qr_token": f"{TAG}{uuid.uuid4().hex[:6]}", "tag": TAG})
    return sid


async def _scan(db, sid, at, used=False, used_by=None):
    aid = f"{TAG}-{uuid.uuid4()}"
    d = {"id": aid, "customer_phone": PHONE, "staff_id": sid, "staff_code": f"{TAG}-S",
         "created_at": _iso(at), "expires_at": _iso(at + timedelta(minutes=15)), "used": used, "tag": TAG}
    if used_by:
        d["used_by_bill_id"] = used_by
    await db.staff_attributions.insert_one(d)
    return aid


async def _bill(db, store, at, amount=500, status="manual_review"):
    bid = f"{TAG}-{uuid.uuid4()}"
    await db.bills.insert_one({"id": bid, "user_phone": PHONE, "store_name": store, "amount": amount,
                               "status": status, "created_at": _iso(at), "tag": TAG})
    return bid


def run(fn):
    async def wrap():
        db = _db(); await _cleanup(db)
        try:
            await fn(db)
        finally:
            await _cleanup(db)
    asyncio.run(wrap())


async def _approve(db, bid, status="approved"):
    await staff_mod.create_or_activate_bill_incentive(bid, PHONE, status)
    await staff_mod.sync_incentive_on_bill_status_change(bid, status)


# --- Binding: latest scan within window, used-latest blocks older unused scans
def test_latest_scan_used_blocks_older_unused():
    async def t(db):
        now = datetime.now(timezone.utc)
        s_old = await _staff(db); s_new = await _staff(db)
        old = await _scan(db, s_old, now - timedelta(minutes=8))
        await _scan(db, s_new, now - timedelta(minutes=3), used=True, used_by=f"{TAG}-other")
        bid = await _bill(db, "Dominos", now)
        await _approve(db, bid, "auto_approved")
        assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
        o = await db.staff_attributions.find_one({"id": old})
        assert o["used"] is False and "used_by_bill_id" not in o
    run(t)


def test_expired_scan_not_bound():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db)
        aid = await _scan(db, sid, now - timedelta(minutes=30))
        bid = await _bill(db, "Dominos", now)
        await _approve(db, bid)
        assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
        assert (await db.staff_attributions.find_one({"id": aid}))["used"] is False
    run(t)


def test_bound_scan_fields_and_alias_brand_match():
    async def t(db):
        now = datetime.now(timezone.utc)
        await db.brands.insert_one({"id": f"{TAG}-b", "brand_name": "P22TEST Brand", "aliases": ["P22TEST Alias"], "tag": TAG})
        sid = await _staff(db, "P22TEST Brand")
        aid = await _scan(db, sid, now - timedelta(minutes=1))
        bid = await _bill(db, "P22TEST-Alias", now)
        await _approve(db, bid)
        a = await db.staff_attributions.find_one({"id": aid})
        assert a["used"] is True and a["used_by_bill_id"] == bid
        rows = await db.staff_incentives.find({"bill_id": bid}).to_list(10)
        assert len(rows) == 1 and rows[0]["staff_id"] == sid and rows[0]["status"] == "redeemable"
        assert rows[0]["attribution_id"] == aid
    run(t)


# --- Mismatch at upload -> correction -> multi-stage approvals: one award, one miss
def test_mismatch_correct_approve_no_dupes():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db, "Dominos")
        aid = await _scan(db, sid, now - timedelta(minutes=2))
        bid = await _bill(db, "Jubilant Foodworks", now)
        await _approve(db, bid, "manual_review")
        await _approve(db, bid, "manual_review")
        assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
        # later scan by another staff after upload must not be used
        s2 = await _staff(db, "Dominos")
        later = await _scan(db, s2, now + timedelta(minutes=1))
        await db.bills.update_one({"id": bid}, {"$set": {"store_name": "Domino's", "status": "approved"}})
        for _ in range(3):
            await _approve(db, bid, "approved")
        rows = await db.staff_incentives.find({"bill_id": bid}).to_list(10)
        assert len(rows) == 1 and rows[0]["staff_id"] == sid and rows[0]["status"] == "redeemable"
        assert rows[0]["attribution_id"] == aid
        assert await db.staff_attribution_misses.count_documents({"bill_id": bid, "reason": "brand_mismatch"}) == 1
        l = await db.staff_attributions.find_one({"id": later})
        assert l["used"] is False and "used_by_bill_id" not in l
    run(t)


def test_later_scan_never_bound_across_reevaluations():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db)
        bid = await _bill(db, "Dominos", now - timedelta(minutes=4))
        await _approve(db, bid, "manual_review")
        later = await _scan(db, sid, now - timedelta(minutes=1))
        await _approve(db, bid, "approved")
        await _approve(db, bid, "approved")
        assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
        l = await db.staff_attributions.find_one({"id": later})
        assert l["used"] is False and "used_by_bill_id" not in l
    run(t)


# --- Rejection handling
def test_reject_after_award_cancels_and_reapprove():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db)
        await _scan(db, sid, now - timedelta(minutes=1))
        bid = await _bill(db, "Dominos", now)
        await _approve(db, bid, "approved")
        await _approve(db, bid, "rejected")
        rows = await db.staff_incentives.find({"bill_id": bid}).to_list(10)
        assert len(rows) == 1 and rows[0]["status"] == "cancelled"
    run(t)


def test_rebound_rejected_bill_creates_no_row():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db)
        await _scan(db, sid, now - timedelta(minutes=1))
        bid = await _bill(db, "Nike", now)
        await _approve(db, bid, "manual_review")
        await db.bills.update_one({"id": bid}, {"$set": {"store_name": "Dominos", "status": "rejected"}})
        await _approve(db, bid, "rejected")
        assert await db.staff_incentives.count_documents({"bill_id": bid}) == 0
        assert await db.staff_attribution_misses.count_documents({"bill_id": bid, "reason": "brand_mismatch"}) == 1
    run(t)


# --- Point 14b registration activation unchanged
def test_registration_activation_brand_gated():
    async def t(db):
        now = datetime.now(timezone.utc)
        sid = await _staff(db, "Dominos")
        rid = f"{TAG}-reg"
        await db.staff_incentives.insert_one({"id": rid, "staff_id": sid, "staff_code": f"{TAG}-S", "customer_phone": PHONE,
                                              "type": "registration", "status": "pending", "amount": 10,
                                              "created_at": _iso(now), "tag": TAG})
        b1 = await _bill(db, "Nike", now)
        await _approve(db, b1, "approved")
        assert (await db.staff_incentives.find_one({"id": rid}))["status"] == "pending"
        assert await db.staff_attribution_misses.count_documents(
            {"bill_id": b1, "reason": "registration_activation_brand_mismatch"}) == 1
        b2 = await _bill(db, "Dominos", now + timedelta(seconds=5))
        await _approve(db, b2, "approved")
        assert (await db.staff_incentives.find_one({"id": rid}))["status"] == "redeemable"
    run(t)


# --- Admin incentive report: alias-aware brand filter + auth
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "CP67Admin@2025"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    d = r.json()
    return d.get("token") or d.get("access_token")


@pytest.fixture(scope="module")
def report_data():
    ids = {}

    async def setup():
        db = _db(); await _cleanup(db)
        await db.brands.insert_one({"id": f"{TAG}-b", "brand_name": "P22TEST Brand", "aliases": ["P22TEST Alias"], "tag": TAG})
        ids["main"] = await _staff(db, "P22TEST Brand")
        ids["alias"] = await _staff(db, "P22TEST-Alias")
        ids["other"] = await _staff(db, "P22TEST Other")
        for k in ("main", "alias", "other"):
            await db.staff_incentives.insert_one({"id": f"{TAG}-inc-{k}", "staff_id": ids[k], "staff_code": f"{TAG}-S",
                                                  "customer_phone": PHONE, "type": "registration", "status": "pending",
                                                  "amount": 10, "created_at": _iso(datetime.now(timezone.utc)), "tag": TAG})
    asyncio.run(setup())
    yield ids
    asyncio.run(_cleanup(_db()))


def _ids(resp):
    return {r["staff_id"] for r in resp.json()["rows"]}


def test_report_brand_filter_alias(admin_token, report_data):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", params={"brand": "P22TEST Brand"}, headers=h, timeout=60)
    assert r.status_code == 200
    got = _ids(r)
    assert report_data["main"] in got and report_data["alias"] in got and report_data["other"] not in got
    r2 = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", params={"brand": "p22test alias"}, headers=h, timeout=60)
    got2 = _ids(r2)
    assert report_data["main"] in got2 and report_data["alias"] in got2 and report_data["other"] not in got2
    r3 = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", params={"brand": "P22TEST Other"}, headers=h, timeout=60)
    assert _ids(r3) == {report_data["other"]}
    r4 = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", params={"brand": "P22TEST Nonexistent"}, headers=h, timeout=60)
    assert r4.status_code == 200 and r4.json()["rows"] == []


def test_report_no_brand_filter_unchanged(admin_token, report_data):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report", params={"staff_id": report_data["other"]}, headers=h, timeout=60)
    assert r.status_code == 200 and _ids(r) == {report_data["other"]}
    assert r.json()["summary"]["total"] == 1


def test_report_csv_alias(admin_token, report_data):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/admin/staff/incentives/report.csv", params={"brand": "P22TEST Alias"}, headers=h, timeout=60)
    assert r.status_code == 200
    body = r.text
    assert "P22TEST Brand" in body and "P22TEST-Alias" in body and "P22TEST Other" not in body


def test_report_auth_rejections(report_data):
    url = f"{BASE_URL}/api/admin/staff/incentives/report"
    assert requests.get(url, timeout=30).status_code in (401, 403)
    st = staff_mod._make_staff_token({"id": report_data["main"], "phone": "7000022099"})
    rm = staff_mod._make_retailer_token({"id": f"{TAG}-rm", "phone": "7000022098"})
    for tok in (st, rm):
        for u in (url, url + ".csv"):
            r = requests.get(u, params={"brand": "P22TEST Brand"}, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
            assert r.status_code == 403, (u, r.status_code)
