#!/usr/bin/env python3
"""Seed/cleanup data for focused browser verification of CP67 Points 5/6/7."""
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient

APP = Path('/app')
SEED_PATH = APP / 'test_reports' / 'bug_verify_points_5_6_7_ui_seed.json'


def read_env(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            out[k] = v.strip().strip('"').strip("'")
    return out


def get_ctx():
    fe = read_env(APP / 'frontend' / '.env')
    be = read_env(APP / 'backend' / '.env')
    api = fe['REACT_APP_BACKEND_URL'].rstrip('/') + '/api'
    db = MongoClient(be.get('MONGO_URL', 'mongodb://localhost:27017'))[be.get('DB_NAME', 'test_database')]
    return api, db


def admin_token(api):
    r = requests.post(f'{api}/admin/login', json={'username': 'admin', 'password': 'CP67Admin@2025'}, timeout=20)
    r.raise_for_status()
    return r.json()['token']


def cleanup():
    api, db = get_ctx()
    if not SEED_PATH.exists():
        print('No seed file to cleanup')
        return
    seed = json.loads(SEED_PATH.read_text())
    staff_id = seed.get('staff_id')
    manager_phone = seed.get('manager_phone')
    brand = seed.get('brand')
    run_id = seed.get('run_id')
    if staff_id:
        db.staff_incentives.delete_many({'staff_id': staff_id})
        db.staff_redemptions.delete_many({'staff_id': staff_id})
        db.retail_staff.delete_many({'id': staff_id})
    if manager_phone:
        db.retailer_managers.delete_many({'phone': manager_phone})
    if brand:
        db.brands.delete_many({'brand_name': brand})
    if run_id:
        db.brands.delete_many({'brand_name': {'$regex': f'^{re.escape("TEST_UI_P567_" + run_id)}'}})
    print(json.dumps({'cleanup': True, 'seed': seed}, indent=2))


def seed():
    cleanup() if SEED_PATH.exists() else None
    api, db = get_ctx()
    token = admin_token(api)
    run_id = uuid.uuid4().hex[:8]
    phone_suffix = str(int(time.time()))[-6:]
    staff_phone = f'89{phone_suffix}11'[-10:]
    manager_phone = f'88{phone_suffix}12'[-10:]
    non_whitelisted_phone = f'87{phone_suffix}13'[-10:]
    brand = f'TEST_UI_P567_{run_id}_Brand'
    category = f'TEST_UI_P567_{run_id}_Category'

    csv_text = f'Brand Name,Brand Category\n{brand},{category}\n'
    r = requests.post(
        f'{api}/admin/staff/catalog/brand-category-mapping',
        headers={'Authorization': f'Bearer {token}'},
        files={'file': ('seed.csv', csv_text.encode('utf-8'), 'text/csv')},
        data={'dry_run': 'false'},
        timeout=30,
    )
    r.raise_for_status()

    r = requests.post(
        f'{api}/admin/staff',
        headers={'Authorization': f'Bearer {token}'},
        json={'name': f'UI P567 Staff {run_id}', 'phone': staff_phone, 'brand_name': brand, 'brand_category': category, 'store_location': 'UI QA'},
        timeout=20,
    )
    r.raise_for_status()
    staff = r.json()['staff']
    staff_id = staff['id']
    now = datetime.now(timezone.utc).isoformat()
    db.staff_incentives.insert_many([
        {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff['staff_code'], 'type': 'bill_upload', 'status': 'redeemable', 'amount': 111, 'created_at': now},
        {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff['staff_code'], 'type': 'registration', 'status': 'redeemed', 'amount': 44, 'created_at': now},
        {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff['staff_code'], 'type': 'registration', 'status': 'pending', 'amount': 33, 'created_at': now},
    ])
    db.staff_redemptions.insert_one({'id': str(uuid.uuid4()), 'reference': f'RDM-UI-{run_id}', 'staff_id': staff_id, 'amount': 111, 'status': 'requested', 'requested_at': now})

    seed_data = {
        'run_id': run_id,
        'api': api,
        'brand': brand,
        'category': category,
        'staff_id': staff_id,
        'staff_phone': staff_phone,
        'staff_code': staff['staff_code'],
        'manager_phone': manager_phone,
        'manager_name': f'UI P567 Manager {run_id}',
        'non_whitelisted_phone': non_whitelisted_phone,
        'expected': {'redeemable': 111, 'redeemed': 44, 'pending': 33},
    }
    SEED_PATH.write_text(json.dumps(seed_data, indent=2))
    print(json.dumps({'seeded': True, **seed_data}, indent=2))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup':
        cleanup()
    else:
        seed()