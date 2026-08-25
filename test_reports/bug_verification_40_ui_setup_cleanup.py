#!/usr/bin/env python3
"""Seed/cleanup helper for iteration 40 browser verification."""
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pymongo import MongoClient

ROOT = Path('/app')
FRONT_ENV = dotenv_values(ROOT / 'frontend' / '.env')
BACK_ENV = dotenv_values(ROOT / 'backend' / '.env')
BASE = (FRONT_ENV.get('REACT_APP_BACKEND_URL') or 'https://staff-points-engine.preview.emergentagent.com').rstrip('/') + '/api'
TEST_PHONE = '9100011122'
TEST_BRAND = 'TEST_BUG_BRAND_XYZ'


def db_cleanup():
    mongo_url = (BACK_ENV.get('MONGO_URL') or 'mongodb://localhost:27017').strip('"')
    db_name = (BACK_ENV.get('DB_NAME') or 'test_database').strip('"')
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
    db = client[db_name]
    a = db.retailer_managers.delete_many({'phone': TEST_PHONE}).deleted_count
    b = db.brands.delete_many({'brand_name': {'$regex': f'^{re.escape(TEST_BRAND)}$', '$options': 'i'}}).deleted_count
    client.close()
    return {'retailer_managers_deleted': a, 'brands_deleted': b}


async def api_seed():
    # Clean first to make POST deterministic.
    clean = db_cleanup()
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        login = await client.post(f'{BASE}/admin/login', json={'username': 'admin', 'password': 'CP67Admin@2025'})
        login.raise_for_status()
        token = login.json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        payload = {'name': 'Bug Test Retailer Manager', 'phone': TEST_PHONE, 'brands': ['Zara'], 'email': 'qa@example.test'}
        r = await client.post(f'{BASE}/admin/staff/retailer-managers', headers=headers, json=payload)
        r.raise_for_status()
        data = {'seeded_manager': r.json()['manager'], 'pre_cleanup': clean, 'base': BASE}
        (ROOT / 'test_reports' / 'bug_verification_40_ui_seed.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(json.dumps(data, indent=2))


async def remove_all_override_for_ui_select_test():
    """Temporarily remove __ALL__ so the UI can prove the All option exists in the picker."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        login = await client.post(f'{BASE}/admin/login', json={'username': 'admin', 'password': 'CP67Admin@2025'})
        login.raise_for_status()
        token = login.json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        r = await client.get(f'{BASE}/admin/staff/config/current', headers=headers)
        r.raise_for_status()
        cfg = r.json()['config']
        backup_path = ROOT / 'test_reports' / 'bug_verification_40_config_backup.json'
        backup_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
        new_cfg = dict(cfg)
        cat = dict(new_cfg.get('category_slabs') or {})
        removed = cat.pop('__ALL__', None)
        new_cfg['category_slabs'] = cat
        if removed is not None:
            put = await client.put(f'{BASE}/admin/staff/config/current', headers=headers, json=new_cfg)
            put.raise_for_status()
        print(json.dumps({'backup': str(backup_path), 'removed_all_override': removed is not None}, indent=2))


async def restore_config_backup():
    backup_path = ROOT / 'test_reports' / 'bug_verification_40_config_backup.json'
    if not backup_path.exists():
        print(json.dumps({'restore_config': 'no backup found'}, indent=2))
        return
    cfg = json.loads(backup_path.read_text(encoding='utf-8'))
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        login = await client.post(f'{BASE}/admin/login', json={'username': 'admin', 'password': 'CP67Admin@2025'})
        login.raise_for_status()
        token = login.json()['token']
        headers = {'Authorization': f'Bearer {token}'}
        put = await client.put(f'{BASE}/admin/staff/config/current', headers=headers, json=cfg)
        put.raise_for_status()
        print(json.dumps({'restore_config': 'ok', 'backup': str(backup_path)}, indent=2))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'cleanup'
    if mode == 'seed':
        asyncio.run(api_seed())
    elif mode == 'prep-config':
        asyncio.run(remove_all_override_for_ui_select_test())
    elif mode == 'restore-config':
        asyncio.run(restore_config_backup())
    elif mode == 'cleanup':
        print(json.dumps({'cleanup': db_cleanup(), 'base': BASE}, indent=2))
    else:
        raise SystemExit(f'unknown mode: {mode}')


if __name__ == '__main__':
    main()