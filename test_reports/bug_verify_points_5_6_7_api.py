#!/usr/bin/env python3
"""
Focused API + persistence verification for CP67 user-reported Points 5, 6, 7.

Runs against the preview backend URL from /app/frontend/.env and uses Mongo only
to seed/cleanup test records that have no public admin endpoint.
"""
import csv
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient


APP = Path('/app')
FRONTEND_ENV = APP / 'frontend' / '.env'
BACKEND_ENV = APP / 'backend' / '.env'


def read_env_file(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        values[k] = v.strip().strip('"').strip("'")
    return values


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def post_csv(session, url, token, text, dry_run=None):
    data = {}
    if dry_run is not None:
        data['dry_run'] = 'true' if dry_run else 'false'
    return session.post(
        url,
        headers={'Authorization': f'Bearer {token}'},
        files={'file': ('test.csv', text.encode('utf-8'), 'text/csv')},
        data=data,
        timeout=30,
    )


def main():
    fe = read_env_file(FRONTEND_ENV)
    be = read_env_file(BACKEND_ENV)
    api = fe['REACT_APP_BACKEND_URL'].rstrip('/') + '/api'
    mongo_url = be.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = be.get('DB_NAME', 'test_database')
    run_id = uuid.uuid4().hex[:8]
    phone_suffix = str(int(time.time()))[-6:]
    staff_phone = f'98{phone_suffix}01'[-10:]
    manager_phone = f'97{phone_suffix}02'[-10:]
    non_whitelisted_phone = f'96{phone_suffix}03'[-10:]
    brand = f'TEST_P567_{run_id}_Brand'
    category = f'TEST_P567_{run_id}_Category'
    category2 = f'TEST_P567_{run_id}_Category2'
    staff_id = manager_id = None
    original_config = None
    client = MongoClient(mongo_url)
    db = client[db_name]
    session = requests.Session()
    evidence = []

    try:
        # Admin login
        r = session.post(f'{api}/admin/login', json={'username': 'admin', 'password': 'CP67Admin@2025'}, timeout=20)
        assert_true(r.status_code == 200, f'admin login failed: {r.status_code} {r.text[:200]}')
        token = r.json()['token']
        evidence.append({'step': 'admin_login', 'status': r.status_code})

        # Point 7: catalog starts usable, mapping template works, dry-run/live mapping update refreshes catalog.
        r = session.get(f'{api}/admin/staff/catalog/brands-categories', headers={'Authorization': f'Bearer {token}'}, timeout=20)
        assert_true(r.status_code == 200, f'catalog failed: {r.status_code} {r.text[:200]}')
        cat0 = r.json()
        assert_true(isinstance(cat0.get('brands'), list) and isinstance(cat0.get('categories'), list), 'catalog shape invalid')
        evidence.append({'step': 'catalog_initial', 'brand_count': len(cat0['brands']), 'category_count': len(cat0['categories'])})

        r = session.get(f'{api}/admin/staff/catalog/brand-category-mapping/template.csv', headers={'Authorization': f'Bearer {token}'}, timeout=20)
        assert_true(r.status_code == 200, f'mapping template failed: {r.status_code}')
        assert_true('brand-category-mapping-template.csv' in r.headers.get('Content-Disposition', ''), 'mapping template filename missing')
        assert_true('Brand Name,Brand Category' in r.text, 'mapping template header invalid')
        evidence.append({'step': 'mapping_template', 'status': r.status_code, 'content_disposition': r.headers.get('Content-Disposition')})

        csv_text = f'Brand Name,Brand Category\n{brand},{category}\n'
        r = post_csv(session, f'{api}/admin/staff/catalog/brand-category-mapping', token, csv_text, dry_run=True)
        assert_true(r.status_code == 200, f'mapping dry-run failed: {r.status_code} {r.text[:200]}')
        dry = r.json()
        assert_true(dry['dry_run'] is True and dry['summary']['created'] >= 1, f'unexpected dry-run summary {dry}')
        assert_true(db.brands.count_documents({'brand_name': brand}) == 0, 'dry-run unexpectedly persisted brand')
        evidence.append({'step': 'mapping_dry_run', 'summary': dry['summary']})

        r = post_csv(session, f'{api}/admin/staff/catalog/brand-category-mapping', token, csv_text, dry_run=False)
        assert_true(r.status_code == 200, f'mapping live failed: {r.status_code} {r.text[:200]}')
        live = r.json()
        assert_true(live['dry_run'] is False and live['summary']['created'] >= 1, f'unexpected live summary {live}')
        evidence.append({'step': 'mapping_live_create', 'summary': live['summary']})

        r = session.get(f'{api}/admin/staff/catalog/brands-categories', headers={'Authorization': f'Bearer {token}'}, timeout=20)
        cat1 = r.json()
        brand_names = [b['brand_name'] for b in cat1['brands']]
        assert_true(brand in brand_names and category in cat1['categories'], 'catalog did not refresh with uploaded brand/category')
        evidence.append({'step': 'catalog_after_mapping', 'new_brand_present': brand in brand_names, 'new_category_present': category in cat1['categories']})

        csv_update = f'Brand Name,Brand Category\n{brand},{category2}\n'
        r = post_csv(session, f'{api}/admin/staff/catalog/brand-category-mapping', token, csv_update, dry_run=False)
        upd = r.json()
        assert_true(r.status_code == 200 and upd['summary']['updated'] >= 1, f'mapping update failed: {r.status_code} {upd}')
        r = session.get(f'{api}/admin/staff/catalog/brands-categories', headers={'Authorization': f'Bearer {token}'}, timeout=20)
        cat2 = r.json()
        assert_true(category2 in cat2['categories'], 'updated category not present in refreshed catalog')
        evidence.append({'step': 'mapping_live_update', 'summary': upd['summary']})

        # Point 7: __ALL__ + both slab kinds round-trip in config.
        r = session.get(f'{api}/admin/staff/config/current', headers={'Authorization': f'Bearer {token}'}, timeout=20)
        assert_true(r.status_code == 200, f'config get failed: {r.status_code}')
        original_config = r.json()['config']
        patch = {
            'registration_slabs': original_config.get('registration_slabs'),
            'bill_upload_slabs': original_config.get('bill_upload_slabs'),
            'category_slabs': dict(original_config.get('category_slabs') or {}),
            'brand_slabs': dict(original_config.get('brand_slabs') or {}),
            'attribution_window_minutes': original_config.get('attribution_window_minutes', 15),
            'registration_validity_days': original_config.get('registration_validity_days', 60),
        }
        patch['category_slabs']['__ALL__'] = {
            'registration_slabs': [{'min': 0, 'max': 999999, 'amount': 321}],
            'bill_upload_slabs': [{'min': 0, 'max': 999999, 'amount': 123}],
        }
        patch['brand_slabs'][brand] = {
            'registration_slabs': [{'min': 0, 'max': 999999, 'amount': 654}],
            'bill_upload_slabs': [{'min': 0, 'max': 999999, 'amount': 456}],
        }
        r = session.put(f'{api}/admin/staff/config/current', headers={'Authorization': f'Bearer {token}'}, json=patch, timeout=20)
        assert_true(r.status_code == 200, f'config put failed: {r.status_code} {r.text[:200]}')
        cfg = r.json()['config']
        assert_true(cfg['category_slabs']['__ALL__']['registration_slabs'][0]['amount'] == 321, '__ALL__ registration slabs did not persist')
        assert_true(cfg['category_slabs']['__ALL__']['bill_upload_slabs'][0]['amount'] == 123, '__ALL__ bill slabs did not persist')
        assert_true(cfg['brand_slabs'][brand]['registration_slabs'][0]['amount'] == 654, 'brand registration slabs did not persist')
        assert_true(cfg['brand_slabs'][brand]['bill_upload_slabs'][0]['amount'] == 456, 'brand bill slabs did not persist')
        evidence.append({'step': 'config_all_and_brand_roundtrip', 'all_key': '__ALL__', 'brand_key': brand})

        # Point 5: admin whitelists manager, retailer OTP login with bypass, dashboard is brand scoped.
        staff_payload = {
            'name': f'P567 Staff {run_id}',
            'phone': staff_phone,
            'brand_name': brand,
            'brand_category': category2,
            'store_location': 'QA Store',
        }
        r = session.post(f'{api}/admin/staff', headers={'Authorization': f'Bearer {token}'}, json=staff_payload, timeout=20)
        assert_true(r.status_code == 200, f'staff create failed: {r.status_code} {r.text[:200]}')
        staff_doc = r.json()['staff']
        staff_id = staff_doc['id']
        now = datetime.now(timezone.utc).isoformat()
        incentives = [
            {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff_doc['staff_code'], 'type': 'bill_upload', 'status': 'redeemable', 'amount': 100, 'created_at': now},
            {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff_doc['staff_code'], 'type': 'registration', 'status': 'redeemed', 'amount': 40, 'created_at': now},
            {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff_doc['staff_code'], 'type': 'registration', 'status': 'pending', 'amount': 25, 'created_at': now},
            {'id': str(uuid.uuid4()), 'staff_id': staff_id, 'staff_code': staff_doc['staff_code'], 'type': 'bill_upload', 'status': 'pending_verification', 'amount': 15, 'created_at': now},
        ]
        db.staff_incentives.insert_many(incentives)
        db.staff_redemptions.insert_one({'id': str(uuid.uuid4()), 'reference': f'RDM-{run_id}', 'staff_id': staff_id, 'amount': 100, 'status': 'requested', 'requested_at': now})
        mgr_payload = {'name': f'P567 Manager {run_id}', 'phone': manager_phone, 'brands': [brand], 'email': f'p567-{run_id}@example.test'}
        r = session.post(f'{api}/admin/staff/retailer-managers', headers={'Authorization': f'Bearer {token}'}, json=mgr_payload, timeout=20)
        assert_true(r.status_code == 200, f'manager create failed: {r.status_code} {r.text[:200]}')
        manager = r.json()['manager']
        manager_id = manager['id']
        evidence.append({'step': 'manager_whitelisted', 'manager_id': manager_id, 'phone': manager_phone, 'brands': [brand]})

        r = session.post(f'{api}/staff/retailer/auth/send-otp', json={'phone': manager_phone}, timeout=20)
        assert_true(r.status_code == 200 and r.json().get('success') is True, f'retailer send-otp failed: {r.status_code} {r.text[:200]}')
        r = session.post(f'{api}/staff/retailer/auth/verify-otp', json={'phone': manager_phone, 'otp': '1234'}, timeout=20)
        assert_true(r.status_code == 200, f'retailer verify failed: {r.status_code} {r.text[:200]}')
        retailer_token = r.json()['token']
        assert_true(r.json()['manager']['phone'] == manager_phone and brand in r.json()['manager']['brands'], 'retailer verify manager payload incorrect')
        r = session.get(f'{api}/staff/retailer/dashboard', headers={'Authorization': f'Bearer {retailer_token}'}, timeout=20)
        assert_true(r.status_code == 200, f'retailer dashboard failed: {r.status_code} {r.text[:200]}')
        dash = r.json()
        assert_true(dash['summary']['redeemable'] == 100, f'redeemable summary wrong: {dash["summary"]}')
        assert_true(dash['summary']['redeemed'] == 40, f'redeemed summary wrong: {dash["summary"]}')
        assert_true(dash['summary']['pending'] == 40, f'pending summary wrong: {dash["summary"]}')
        assert_true(len(dash.get('staff', [])) == 1 and dash['staff'][0]['brand_name'] == brand, 'dashboard staff list not brand-scoped')
        assert_true(any(r.get('reference') == f'RDM-{run_id}' for r in dash.get('redemptions', [])), 'dashboard redemptions missing seeded redemption')
        evidence.append({'step': 'retailer_dashboard', 'summary': dash['summary'], 'staff_rows': len(dash['staff']), 'redemption_rows': len(dash.get('redemptions', []))})

        r = session.post(f'{api}/staff/retailer/auth/send-otp', json={'phone': non_whitelisted_phone}, timeout=20)
        assert_true(r.status_code == 200, 'non-whitelisted send-otp should not reveal registration status')
        r = session.post(f'{api}/staff/retailer/auth/verify-otp', json={'phone': non_whitelisted_phone, 'otp': '1234'}, timeout=20)
        assert_true(r.status_code == 401, f'non-whitelisted verify should 401, got {r.status_code} {r.text[:200]}')
        evidence.append({'step': 'non_whitelisted_verify', 'status': r.status_code, 'detail': r.json().get('detail')})

        # Point 6: invalid/expired admin token fetches return 401, allowing frontend handle401 to intercept.
        bad = 'garbage'
        checks = []
        r = session.get(f'{api}/admin/me', headers={'Authorization': f'Bearer {bad}'}, timeout=20)
        checks.append({'endpoint': 'GET /admin/me', 'status': r.status_code, 'detail': r.json().get('detail')})
        r = session.get(f'{api}/admin/staff/bulk-import/template.csv', headers={'Authorization': f'Bearer {bad}'}, timeout=20)
        checks.append({'endpoint': 'GET /admin/staff/bulk-import/template.csv', 'status': r.status_code, 'detail': r.json().get('detail')})
        r = post_csv(session, f'{api}/admin/staff/bulk-import', bad, 'Brand Name,Staff Name,Contact No.\nX,Y,9999999999\n', dry_run=True)
        checks.append({'endpoint': 'POST /admin/staff/bulk-import', 'status': r.status_code, 'detail': r.json().get('detail')})
        r = session.get(f'{api}/admin/staff/catalog/brand-category-mapping/template.csv', headers={'Authorization': f'Bearer {bad}'}, timeout=20)
        checks.append({'endpoint': 'GET /admin/staff/catalog/brand-category-mapping/template.csv', 'status': r.status_code, 'detail': r.json().get('detail')})
        r = post_csv(session, f'{api}/admin/staff/catalog/brand-category-mapping', bad, csv_text, dry_run=True)
        checks.append({'endpoint': 'POST /admin/staff/catalog/brand-category-mapping', 'status': r.status_code, 'detail': r.json().get('detail')})
        assert_true(all(c['status'] == 401 for c in checks), f'not all invalid-token checks returned 401: {checks}')
        evidence.append({'step': 'invalid_token_api_statuses', 'checks': checks})

        print(json.dumps({'ok': True, 'api': api, 'evidence': evidence}, indent=2))
    finally:
        # Best-effort cleanup / restore.
        if original_config is not None:
            try:
                session.put(
                    f'{api}/admin/staff/config/current',
                    headers={'Authorization': f'Bearer {token}'},
                    json={
                        'registration_slabs': original_config.get('registration_slabs'),
                        'bill_upload_slabs': original_config.get('bill_upload_slabs'),
                        'category_slabs': original_config.get('category_slabs') or {},
                        'brand_slabs': original_config.get('brand_slabs') or {},
                        'attribution_window_minutes': original_config.get('attribution_window_minutes', 15),
                        'registration_validity_days': original_config.get('registration_validity_days', 60),
                    },
                    timeout=20,
                )
            except Exception as e:
                print(f'cleanup warning: failed to restore config: {e}')
        try:
            db.staff_incentives.delete_many({'staff_id': staff_id})
            db.staff_redemptions.delete_many({'staff_id': staff_id})
            if staff_id:
                db.retail_staff.delete_many({'id': staff_id})
            if manager_id:
                db.retailer_managers.delete_many({'id': manager_id})
            db.brands.delete_many({'brand_name': {'$regex': f'^{re.escape("TEST_P567_" + run_id)}'}})
        except Exception as e:
            print(f'cleanup warning: mongo cleanup failed: {e}')


if __name__ == '__main__':
    main()