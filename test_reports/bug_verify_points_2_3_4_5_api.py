#!/usr/bin/env python3
"""
Focused bug verification for CP67 Staff Incentive feedback Points 2/3/4/5.

Creates isolated test data, verifies the preview API behavior end-to-end, and
cleans up seeded records. This is a QA artifact only; it does not modify
product code.
"""
import csv
import io
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import jwt
import requests
from pymongo import MongoClient


APP = Path("/app")
OLD_WA = "917988077663"
EXPECTED_WA = "917347576767"
ADMIN_USER = "admin"
ADMIN_PASS = "CP67Admin@2025"
OTP = "1234"


def read_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


frontend_env = read_env(APP / "frontend" / ".env")
backend_env = read_env(APP / "backend" / ".env")
BASE = frontend_env.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = BASE + "/api"
MONGO_URL = backend_env.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = backend_env.get("DB_NAME", "test_database")


class CheckFailed(AssertionError):
    pass


results = []


def check(name, condition, detail=""):
    if condition:
        print(f"PASS: {name} {detail}")
        results.append({"name": name, "status": "pass", "detail": detail})
    else:
        print(f"FAIL: {name} {detail}")
        results.append({"name": name, "status": "fail", "detail": detail})
        raise CheckFailed(f"{name}: {detail}")


def request_json(method, url, **kwargs):
    r = requests.request(method, url, timeout=25, **kwargs)
    try:
        data = r.json()
    except Exception:
        data = {"_raw": r.text[:500]}
    return r, data


def no_pii(obj):
    banned_keys = {"customer_phone", "customer_name", "customer", "bill_image", "bill_image_url", "image_url"}
    found = []

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                lk = k.lower()
                next_path = f"{path}.{k}" if path else k
                if lk in banned_keys or "customer_phone" in lk or "bill_image" in lk:
                    found.append(next_path)
                walk(v, next_path)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")

    walk(obj)
    return found


def main():
    print(f"Using API base: {API}")
    print(f"Using Mongo DB: {DB_NAME}")
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    client.admin.command("ping")

    run = str(int(time.time()))[-6:]
    brand_main = f"QA-P2345-Brand-{run}"
    brand_other = f"QA-P2345-Other-{run}"
    category_main = f"QA-P2345-Category-{run}"
    category_import = f"QA-P2345-ImportCat-{run}"
    phone_staff_main = "9000" + run
    phone_staff_other = "9001" + run
    phone_import_1 = "9911" + run
    phone_import_2 = "9912" + run
    phone_mgr = "9002" + run
    phone_unlisted = "9003" + run
    seed_marker = f"bug_verify_points_2_3_4_5_{run}"

    admin_token = None
    original_config = None
    created_staff_ids = []
    created_manager_id = None
    inserted_incentive_ids = []
    inserted_redemption_ids = []

    try:
        # Admin auth
        r, data = request_json("POST", f"{API}/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
        check("admin login", r.status_code == 200 and data.get("token"), f"status={r.status_code}")
        admin_token = data["token"]
        ah = {"Authorization": f"Bearer {admin_token}"}

        # Seed two staff via admin API for QR and retailer dashboard scope testing.
        for name, phone, brand, category in [
            ("QA Main Staff", phone_staff_main, brand_main, category_main),
            ("QA Other Staff", phone_staff_other, brand_other, category_main),
        ]:
            payload = {"name": f"{name} {run}", "phone": phone, "brand_name": brand, "brand_category": category, "store_location": seed_marker}
            r, data = request_json("POST", f"{API}/admin/staff", headers=ah, json=payload)
            check(f"create staff {brand}", r.status_code == 200 and data.get("staff", {}).get("id"), f"status={r.status_code}")
            created_staff_ids.append(data["staff"]["id"])

        main_staff_id, other_staff_id = created_staff_ids

        # Point 2: Admin QR must use correct WhatsApp number and never old fallback.
        r, qr = request_json("GET", f"{API}/admin/staff/{main_staff_id}/qr", headers=ah)
        wa_url = qr.get("whatsapp_url", "")
        check("Point 2 admin QR uses WHATSAPP_NUMBER", r.status_code == 200 and EXPECTED_WA in wa_url and OLD_WA not in wa_url, wa_url[:180])

        # Point 2: PDF endpoint works for same staff and binary does not expose the old fallback.
        r = requests.get(f"{API}/admin/staff/qr-cards.pdf?ids={main_staff_id}", headers=ah, timeout=25)
        check(
            "Point 2 QR cards PDF returns PDF without old fallback bytes",
            r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf") and len(r.content) > 1000 and OLD_WA.encode() not in r.content,
            f"status={r.status_code}, content-type={r.headers.get('content-type')}, bytes={len(r.content)}",
        )

        # Point 2: Staff self QR after OTP login must use correct WhatsApp number.
        r, _ = request_json("POST", f"{API}/staff/auth/send-otp", json={"phone": phone_staff_main})
        check("staff OTP send", r.status_code == 200, f"status={r.status_code}")
        r, staff_login = request_json("POST", f"{API}/staff/auth/verify-otp", json={"phone": phone_staff_main, "otp": OTP})
        staff_token = staff_login.get("token")
        check("staff OTP verify with dev bypass", r.status_code == 200 and staff_token, f"status={r.status_code}")
        r, self_qr = request_json("GET", f"{API}/staff/qr", headers={"Authorization": f"Bearer {staff_token}"})
        self_wa = self_qr.get("whatsapp_url", "")
        check("Point 2 staff self QR uses WHATSAPP_NUMBER", r.status_code == 200 and EXPECTED_WA in self_wa and OLD_WA not in self_wa, self_wa[:180])

        # Point 3: Category-wise and brand-wise slabs save and round-trip.
        r, cfg = request_json("GET", f"{API}/admin/staff/config/current", headers=ah)
        check("Point 3 get current config", r.status_code == 200 and cfg.get("config"), f"status={r.status_code}")
        original_config = cfg["config"]
        update_payload = dict(original_config)
        update_payload.pop("_id", None)
        update_payload["category_slabs"] = {
            category_main: {
                "registration_slabs": [{"min": 0, "max": 99, "amount": 321}],
                "bill_upload_slabs": [{"min": 0, "max": 99, "amount": 45}],
            }
        }
        update_payload["brand_slabs"] = {
            brand_main: {
                "registration_slabs": [{"min": 0, "max": 99, "amount": 654}],
                "bill_upload_slabs": [{"min": 0, "max": 99, "amount": 76}],
            }
        }
        r, updated = request_json("PUT", f"{API}/admin/staff/config/current", headers=ah, json=update_payload)
        check("Point 3 PUT category_slabs and brand_slabs", r.status_code == 200, f"status={r.status_code}")
        r, roundtrip = request_json("GET", f"{API}/admin/staff/config/current", headers=ah)
        rt_cfg = roundtrip.get("config", {})
        check(
            "Point 3 config round-trips category-wise + brand-wise slabs",
            r.status_code == 200
            and rt_cfg.get("category_slabs", {}).get(category_main, {}).get("registration_slabs", [{}])[0].get("amount") == 321
            and rt_cfg.get("brand_slabs", {}).get(brand_main, {}).get("bill_upload_slabs", [{}])[0].get("amount") == 76,
            json.dumps({"category_slabs": rt_cfg.get("category_slabs"), "brand_slabs": rt_cfg.get("brand_slabs")})[:300],
        )

        # Point 4a: Template exact header.
        r = requests.get(f"{API}/admin/staff/bulk-import/template.csv", headers=ah, timeout=25)
        first_line = r.text.splitlines()[0] if r.text else ""
        check("Point 4 template CSV exact header", r.status_code == 200 and first_line == "Mob No,Name of Employee,Brand Name,Brand Category", first_line)

        # Point 4b/d: Live CSV import with exact columns, brand_category populated, brands auto-upserted.
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["Mob No", "Name of Employee", "Brand Name", "Brand Category"])
        writer.writerow([phone_import_1, f"QA Import One {run}", f"{brand_main}-Import", category_import])
        writer.writerow([phone_import_2, f"QA Import Two {run}", f"{brand_main}-Import", category_import])
        files = {"file": ("staff-template-import.csv", csv_buf.getvalue().encode("utf-8"), "text/csv")}
        r, imported = request_json("POST", f"{API}/admin/staff/bulk-import", headers=ah, files=files, data={"dry_run": "false"})
        check("Point 4 bulk import accepts exact columns", r.status_code == 200 and imported.get("summary", {}).get("imported") == 2, json.dumps(imported.get("summary", {})))
        imported_docs = list(db.retail_staff.find({"phone": {"$in": [phone_import_1, phone_import_2]}}, {"_id": 0}))
        created_staff_ids.extend([d["id"] for d in imported_docs])
        check("Point 4 imported staff have brand_category", len(imported_docs) == 2 and all(d.get("brand_category") == category_import for d in imported_docs), json.dumps(imported_docs, default=str)[:300])
        brand_doc = db.brands.find_one({"brand_name": {"$regex": f"^{re.escape(brand_main + '-Import')}$", "$options": "i"}}, {"_id": 0})
        check("Point 4 import auto-upserts brand with category", bool(brand_doc and brand_doc.get("category") == category_import), json.dumps(brand_doc, default=str))

        # Point 5: Seed manager + incentives containing PII fields; dashboard must omit PII.
        r, mgr = request_json("POST", f"{API}/admin/staff/retailer-managers", headers=ah, json={"name": f"QA Manager {run}", "phone": phone_mgr, "brands": [brand_main]})
        created_manager_id = mgr.get("manager", {}).get("id")
        check("Point 5 admin creates retailer manager", r.status_code == 200 and created_manager_id, f"status={r.status_code}")

        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        incentive_docs = [
            {"id": str(uuid.uuid4()), "staff_id": main_staff_id, "type": "registration", "status": "redeemable", "amount": 111, "created_at": now, "customer_phone": "9999999999", "customer_name": "Hidden Customer", "bill_image": "https://private.example/bill.jpg", "source": seed_marker},
            {"id": str(uuid.uuid4()), "staff_id": main_staff_id, "type": "bill_upload", "status": "redeemed", "amount": 22, "created_at": now, "customer_phone": "9888888888", "source": seed_marker},
            {"id": str(uuid.uuid4()), "staff_id": main_staff_id, "type": "bill_upload", "status": "pending", "amount": 33, "created_at": now, "customer_name": "Hidden Two", "source": seed_marker},
            {"id": str(uuid.uuid4()), "staff_id": other_staff_id, "type": "registration", "status": "redeemable", "amount": 9999, "created_at": now, "customer_phone": "9777777777", "source": seed_marker},
        ]
        db.staff_incentives.insert_many(incentive_docs)
        inserted_incentive_ids = [d["id"] for d in incentive_docs]
        red_doc = {"id": str(uuid.uuid4()), "staff_id": main_staff_id, "reference": f"QA-RED-{run}", "amount": 22, "status": "settled", "requested_at": now, "customer_phone": "9666666666", "source": seed_marker}
        db.staff_redemptions.insert_one(red_doc)
        inserted_redemption_ids = [red_doc["id"]]

        r, _ = request_json("POST", f"{API}/staff/retailer/auth/send-otp", json={"phone": phone_mgr})
        check("Point 5 whitelisted retailer send OTP", r.status_code == 200, f"status={r.status_code}")
        r, retailer_login = request_json("POST", f"{API}/staff/retailer/auth/verify-otp", json={"phone": phone_mgr, "otp": OTP})
        retailer_token = retailer_login.get("token")
        payload = jwt.decode(retailer_token, options={"verify_signature": False}) if retailer_token else {}
        check("Point 5 whitelisted retailer verify OTP returns retailer_manager JWT", r.status_code == 200 and payload.get("role") == "retailer_manager", json.dumps(payload))

        r, unlisted = request_json("POST", f"{API}/staff/retailer/auth/verify-otp", json={"phone": phone_unlisted, "otp": OTP})
        check("Point 5 non-whitelisted phone is rejected", r.status_code == 401, f"status={r.status_code}, body={unlisted}")

        r, dash = request_json("GET", f"{API}/staff/retailer/dashboard", headers={"Authorization": f"Bearer {retailer_token}"})
        summary = dash.get("summary", {})
        staff_rows = dash.get("staff", [])
        pii_paths = no_pii(dash)
        check(
            "Point 5 retailer dashboard summary/staff/redemptions and no consumer PII",
            r.status_code == 200
            and summary.get("redeemable") == 111
            and summary.get("redeemed") == 22
            and summary.get("pending") == 33
            and summary.get("total_staff") == 1
            and len(staff_rows) == 1
            and staff_rows[0].get("brand_name") == brand_main
            and dash.get("redemptions")
            and not pii_paths,
            json.dumps({"summary": summary, "staff": staff_rows, "pii_paths": pii_paths, "redemptions": dash.get("redemptions")}, default=str)[:600],
        )

        print("\nALL API CHECKS PASSED")
        return 0
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        return 1
    finally:
        # Restore config to avoid leaving QA slab overrides behind.
        if admin_token and original_config:
            try:
                original_config.pop("_id", None)
                requests.put(f"{API}/admin/staff/config/current", headers={"Authorization": f"Bearer {admin_token}"}, json=original_config, timeout=20)
                print("Cleanup: restored original staff config")
            except Exception as e:
                print(f"Cleanup warning: config restore failed: {e}")
        try:
            if created_staff_ids:
                db.retail_staff.delete_many({"id": {"$in": created_staff_ids}})
            if inserted_incentive_ids:
                db.staff_incentives.delete_many({"id": {"$in": inserted_incentive_ids}})
            if inserted_redemption_ids:
                db.staff_redemptions.delete_many({"id": {"$in": inserted_redemption_ids}})
            if created_manager_id:
                db.retailer_managers.delete_one({"id": created_manager_id})
            db.brands.delete_many({"brand_name": {"$in": [f"{brand_main}-Import"]}})
            db.staff_otps.delete_many({"phone": {"$in": [phone_staff_main, phone_mgr, phone_unlisted]}})
            print("Cleanup: removed seeded QA records")
        except Exception as e:
            print(f"Cleanup warning: data cleanup failed: {e}")


if __name__ == "__main__":
    sys.exit(main())