#!/usr/bin/env python3
"""Focused API verification for Retailer Incentive Points 5/6/7.

Targets the preview API from frontend .env. Creates temporary manager/mapping
data and removes it after verification.
"""
import asyncio
import json
import os
import re
from pathlib import Path

import httpx
import jwt
from dotenv import dotenv_values
from pymongo import MongoClient


ROOT = Path('/app')
FRONT_ENV = dotenv_values(ROOT / 'frontend' / '.env')
BACK_ENV = dotenv_values(ROOT / 'backend' / '.env')
BASE = (FRONT_ENV.get('REACT_APP_BACKEND_URL') or 'https://mall-engagement-hub.preview.emergentagent.com').rstrip('/') + '/api'
ADMIN_USER = 'admin'
ADMIN_PASS = 'CP67Admin@2025'
TEST_PHONE = '9100011122'
TEST_BRAND = 'TEST_BUG_BRAND_XYZ'


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def collect_keys(obj):
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= collect_keys(item)
    return keys


def cleanup_db():
    """Best-effort direct DB cleanup for temp docs created by this script."""
    mongo_url = (BACK_ENV.get('MONGO_URL') or 'mongodb://localhost:27017').strip('"')
    db_name = (BACK_ENV.get('DB_NAME') or 'test_database').strip('"')
    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        db = client[db_name]
        db.retailer_managers.delete_many({'phone': TEST_PHONE})
        db.brands.delete_many({'brand_name': {'$regex': f'^{re.escape(TEST_BRAND)}$', '$options': 'i'}})
        client.close()
        return True
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask test result
        print(f'WARN: DB cleanup failed: {exc}')
        return False


async def main():
    cleanup_db()
    result = {
        'base': BASE,
        'checks': [],
        'manager_id': None,
        'cleanup_db_attempted': False,
    }
    original_config = None
    manager_id = None

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        def ok(name, details=None):
            result['checks'].append({'name': name, 'status': 'passed', 'details': details or {}})
            print(f'PASS: {name}')

        # Admin login
        r = await client.post(f'{BASE}/admin/login', json={'username': ADMIN_USER, 'password': ADMIN_PASS})
        assert_true(r.status_code == 200, f'admin login failed: HTTP {r.status_code} {r.text[:200]}')
        token = r.json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        ok('admin_login')

        # Point 5 retailer manager CRUD + OTP dashboard
        payload = {'name': 'Bug Test Retailer Manager', 'phone': TEST_PHONE, 'brands': ['Zara'], 'email': 'qa@example.test'}
        r = await client.post(f'{BASE}/admin/staff/retailer-managers', headers=headers, json=payload)
        assert_true(r.status_code == 200, f'create manager failed: HTTP {r.status_code} {r.text[:200]}')
        manager = r.json()['manager']
        manager_id = manager['id']
        result['manager_id'] = manager_id
        ok('create_retailer_manager', {'id': manager_id, 'phone': manager['phone'], 'brands': manager['brands']})

        r = await client.post(f'{BASE}/staff/retailer/auth/send-otp', json={'phone': TEST_PHONE})
        assert_true(r.status_code == 200 and r.json().get('success') is True, f'send OTP failed: {r.status_code} {r.text[:200]}')
        ok('retailer_send_otp')

        r = await client.post(f'{BASE}/staff/retailer/auth/verify-otp', json={'phone': TEST_PHONE, 'otp': '1234'})
        assert_true(r.status_code == 200, f'verify OTP failed: HTTP {r.status_code} {r.text[:200]}')
        retailer_token = r.json()['token']
        decoded = jwt.decode(retailer_token, options={'verify_signature': False})
        assert_true(decoded.get('role') == 'retailer_manager', f'token role not retailer_manager: {decoded}')
        ok('retailer_verify_otp_role', {'role': decoded.get('role')})

        r = await client.get(f'{BASE}/staff/retailer/dashboard', headers={'Authorization': f'Bearer {retailer_token}'})
        assert_true(r.status_code == 200, f'retailer dashboard failed: HTTP {r.status_code} {r.text[:200]}')
        dash = r.json()
        assert_true(all(k in dash for k in ['manager', 'summary', 'staff', 'redemptions']), 'dashboard missing required top-level sections')
        forbidden = {'customer_phone', 'customer_name', 'bill_image', 'purchase_value', 'bill_id'}
        leaked = collect_keys(dash) & forbidden
        assert_true(not leaked, f'dashboard leaked forbidden keys: {sorted(leaked)}')
        non_zara_staff = [s for s in dash.get('staff', []) if (s.get('brand_name') or '').lower() != 'zara']
        assert_true(not non_zara_staff, f'dashboard returned non-Zara staff rows: {non_zara_staff[:3]}')
        ok('retailer_dashboard_no_pii_brand_scoped', {'staff_count': len(dash.get('staff', [])), 'summary': dash.get('summary')})

        r = await client.post(f'{BASE}/staff/retailer/auth/verify-otp', json={'phone': '9199991999', 'otp': '1234'})
        assert_true(r.status_code == 401, f'non-whitelisted phone expected 401, got HTTP {r.status_code}: {r.text[:200]}')
        ok('non_whitelisted_retailer_verify_rejected')

        # Point 6 API side: bad admin token returns 401; UI tests verify friendly handling.
        r = await client.get(f'{BASE}/admin/staff/bulk-import/template.csv', headers={'Authorization': 'Bearer garbage.jwt'})
        assert_true(r.status_code == 401, f'bad admin token expected 401, got {r.status_code}')
        assert_true('Invalid token' in r.text or 'Token' in r.text, 'bad-token API did not return token auth error')
        ok('bad_token_api_returns_401_for_ui_handling')

        # Point 7 catalog + templates + mapping upload.
        r = await client.get(f'{BASE}/admin/staff/catalog/brands-categories', headers=headers)
        assert_true(r.status_code == 200, f'catalog failed: {r.status_code} {r.text[:200]}')
        catalog = r.json()
        categories = catalog.get('categories') or []
        brands = catalog.get('brands') or []
        brand_names = [b.get('brand_name') for b in brands]
        assert_true(len(categories) >= 15, f'expected >=15 categories, got {len(categories)}')
        assert_true(len(brands) >= 100, f'expected >=100 brands, got {len(brands)}')
        for expected in ['Fashion', 'Electronics']:
            assert_true(any(c.lower() == expected.lower() for c in categories), f'missing category {expected}')
        assert_true(any('food' in c.lower() and 'beverage' in c.lower() for c in categories), 'missing Food & Beverage category')
        for expected in ['Zara', 'Adidas', 'Apple']:
            assert_true(any((b or '').lower() == expected.lower() for b in brand_names), f'missing brand {expected}')
        ok('catalog_dropdown_sources', {'category_count': len(categories), 'brand_count': len(brands)})

        r = await client.get(f'{BASE}/admin/staff/catalog/brand-category-mapping/template.csv', headers=headers)
        assert_true(r.status_code == 200, f'mapping template failed: {r.status_code} {r.text[:200]}')
        assert_true(r.text.startswith('Brand Name,Brand Category'), f'mapping template header wrong: {r.text[:80]}')
        ok('brand_category_mapping_template_header')

        csv_bytes = f'Brand Name,Brand Category\n{TEST_BRAND},Fashion\n'.encode()
        files = {'file': ('brand-map.csv', csv_bytes, 'text/csv')}
        data = {'dry_run': 'false'}
        r = await client.post(f'{BASE}/admin/staff/catalog/brand-category-mapping', headers=headers, data=data, files=files)
        assert_true(r.status_code == 200, f'mapping upload failed: {r.status_code} {r.text[:200]}')
        up = r.json()
        assert_true(up.get('success') is True and up.get('dry_run') is False, f'mapping upload unexpected response: {up}')
        assert_true(up.get('summary', {}).get('created', 0) >= 1 or up.get('summary', {}).get('updated', 0) >= 1, f'mapping upload did not create/update: {up}')
        ok('brand_category_mapping_live_upload', {'summary': up.get('summary')})

        r = await client.get(f'{BASE}/admin/staff/catalog/brands-categories', headers=headers)
        assert_true(r.status_code == 200, f'catalog after upload failed: {r.status_code}')
        brand_names_after = [b.get('brand_name') for b in (r.json().get('brands') or [])]
        assert_true(TEST_BRAND in brand_names_after, 'uploaded brand not present in catalog')
        ok('uploaded_brand_visible_in_catalog')

        # __ALL__ override persistence, then restore original config.
        r = await client.get(f'{BASE}/admin/staff/config/current', headers=headers)
        assert_true(r.status_code == 200, f'config GET failed: {r.status_code} {r.text[:200]}')
        original_config = r.json()['config']
        test_all = {
            'registration_slabs': [{'min': 0, 'max': 3, 'amount': 67}, {'min': 4, 'max': 999999, 'amount': 77}],
            'bill_upload_slabs': [{'min': 0, 'max': 5, 'amount': 57}, {'min': 6, 'max': 999999, 'amount': 87}],
        }
        new_config = dict(original_config)
        cat_slabs = dict(new_config.get('category_slabs') or {})
        cat_slabs['__ALL__'] = test_all
        new_config['category_slabs'] = cat_slabs
        r = await client.put(f'{BASE}/admin/staff/config/current', headers=headers, json=new_config)
        assert_true(r.status_code == 200, f'config PUT __ALL__ failed: {r.status_code} {r.text[:200]}')
        r = await client.get(f'{BASE}/admin/staff/config/current', headers=headers)
        assert_true(r.status_code == 200, f'config verify GET failed: {r.status_code}')
        got_all = r.json()['config'].get('category_slabs', {}).get('__ALL__')
        assert_true(got_all == test_all, f'__ALL__ rows mismatch: got {got_all}, expected {test_all}')
        ok('__ALL___slabs_persist_exactly', got_all)

        # Regression sanity: QR URL + bulk staff template.
        r = await client.get(f'{BASE}/admin/staff', headers=headers)
        assert_true(r.status_code == 200, f'staff list failed: {r.status_code}')
        staff_list = r.json().get('staff') or []
        assert_true(staff_list, 'staff list empty; cannot verify QR URL regression without creating permanent staff via API')
        staff_id = staff_list[0]['id']
        r = await client.get(f'{BASE}/admin/staff/{staff_id}/qr', headers=headers)
        assert_true(r.status_code == 200, f'QR endpoint failed: {r.status_code} {r.text[:200]}')
        wa = r.json().get('whatsapp_url') or ''
        assert_true('917347576767' in wa, f'QR URL missing correct WhatsApp number: {wa}')
        assert_true('917988077663' not in wa, f'QR URL contains old WhatsApp number: {wa}')
        ok('staff_qr_url_whatsapp_number')

        r = await client.get(f'{BASE}/admin/staff/bulk-import/template.csv', headers=headers)
        assert_true(r.status_code == 200, f'bulk import template failed: {r.status_code} {r.text[:200]}')
        assert_true(r.text.startswith('Mob No,Name of Employee,Brand Name,Brand Category'), f'bulk template header wrong: {r.text[:100]}')
        ok('bulk_import_template_header')

        # Cleanup API-created manager and restore config.
        if manager_id:
            r = await client.delete(f'{BASE}/admin/staff/retailer-managers/{manager_id}', headers=headers)
            assert_true(r.status_code == 200, f'manager cleanup delete failed: {r.status_code} {r.text[:200]}')
            ok('cleanup_manager_api')
        if original_config is not None:
            r = await client.put(f'{BASE}/admin/staff/config/current', headers=headers, json=original_config)
            assert_true(r.status_code == 200, f'config restore failed: {r.status_code} {r.text[:200]}')
            ok('cleanup_restore_config')

    result['cleanup_db_attempted'] = cleanup_db()
    result['status'] = 'passed'
    out = ROOT / 'test_reports' / 'bug_verification_40_api_output.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())