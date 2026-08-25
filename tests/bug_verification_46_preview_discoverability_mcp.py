import asyncio
import json
import re
import time
from pathlib import Path

BASE_URL = "https://staff-points-engine.preview.emergentagent.com"
USERNAME = "admin"
PASSWORD = "CP67Admin@2025"
OUT_DIR = Path("/app/test_reports/ui_46")
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def expect_visible(testid, timeout=15000):
    loc = page.locator(f'[data-testid="{testid}"]')
    await loc.wait_for(state="visible", timeout=timeout)
    print(f"PASS visible: {testid}")
    return loc


def extract_count(label, body_text):
    m = re.search(rf"{re.escape(label)} \\(([^)]+)\\)", body_text)
    return m.group(1) if m else None


async def body_text():
    return await page.locator("body").inner_text()


async def api_get(path):
    return await page.evaluate(
        """async ({base, path}) => {
            const token = localStorage.getItem('cp67_token');
            const r = await fetch(`${base}/api${path}`, {headers: {Authorization: `Bearer ${token}`}});
            let data = {};
            try { data = await r.json(); } catch (e) { data = {parseError: String(e)}; }
            return {status: r.status, ok: r.ok, data};
        }""",
        {"base": BASE_URL, "path": path},
    )


async def api_post(path, payload):
    return await page.evaluate(
        """async ({base, path, payload}) => {
            const token = localStorage.getItem('cp67_token');
            const r = await fetch(`${base}/api${path}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
                body: JSON.stringify(payload)
            });
            let data = {};
            try { data = await r.json(); } catch (e) { data = {parseError: String(e)}; }
            return {status: r.status, ok: r.ok, data};
        }""",
        {"base": BASE_URL, "path": path, "payload": payload},
    )


async def table_rows(testid):
    return await page.evaluate(
        """(testid) => Array.from(document.querySelectorAll(`[data-testid="${testid}"] tr`)).map(tr =>
            Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
        )""",
        testid,
    )


async def upload_live(input_testid, file_path, dialog_label):
    def _handle_dialog(dialog):
        print(f"Dialog for {dialog_label}: {dialog.message[:120]}")
        asyncio.create_task(dialog.dismiss())  # In this app Cancel/dismiss performs LIVE import/upload; OK is dry-run.
    page.once("dialog", _handle_dialog)
    await page.locator(f'[data-testid="{input_testid}"]').set_input_files(str(file_path))
    await page.wait_for_timeout(1000)


try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    await page.evaluate("localStorage.removeItem('cp67_token')")
    await page.reload(wait_until="domcontentloaded")
    await expect_visible("login-username-input")
    await page.locator('[data-testid="login-username-input"]').fill(USERNAME)
    await page.locator('[data-testid="login-password-input"]').fill(PASSWORD)
    await page.locator('[data-testid="login-submit-btn"]').click()
    await page.wait_for_function("() => !!localStorage.getItem('cp67_token')", timeout=15000)
    print("PASS login: admin token stored on preview")

    # Point 27 — Staff import discoverability.
    await page.goto(f"{BASE_URL}/staff-incentives", wait_until="domcontentloaded")
    await expect_visible("staff-incentives-page")
    await expect_visible("staff-filter-bar")
    for tid in ["staff-search-input", "staff-brand-filter", "staff-recent-toggle", "staff-page-size"]:
        await expect_visible(tid)

    staff_resp = await api_get("/admin/staff")
    assert staff_resp["ok"], f"GET /admin/staff failed: {staff_resp}"
    staff = staff_resp["data"].get("staff", [])
    staff_total = staff_resp["data"].get("total", len(staff))
    assert staff_total == len(staff) and staff_total > 0, f"Unexpected staff total: {staff_total}, len={len(staff)}"
    await page.wait_for_function("(t) => document.body.innerText.includes(t)", arg=f"Retail Staff ({staff_total})", timeout=15000)
    print(f"PASS staff header total: Retail Staff ({staff_total}) matches API total")

    target_staff = next(s for s in staff if s.get("staff_code"))
    query = target_staff["staff_code"]
    expected_matches = [
        s for s in staff
        if query.lower() in " ".join([str(s.get(k) or "") for k in ["name", "phone", "staff_code", "brand_name", "store_location"]]).lower()
    ]
    await page.locator('[data-testid="staff-search-input"]').fill(query)
    await page.wait_for_timeout(500)
    body = await body_text()
    visible_count = extract_count("Retail Staff", body)
    expected_label = f"{len(expected_matches)} of {staff_total}" if len(expected_matches) != staff_total else str(staff_total)
    assert visible_count == expected_label, f"Staff search header expected {expected_label}, got {visible_count}"
    rows = await table_rows("staff-list-tbody")
    assert any(row and row[0] == query for row in rows), f"Searched staff_code {query} not visible in table rows {rows[:3]}"
    print(f"PASS staff search: {query} narrows header to Retail Staff ({visible_count}) and row is visible")

    await page.locator('[data-testid="staff-search-input"]').fill("")
    if not await page.locator('[data-testid="staff-recent-toggle"]').is_checked():
        await page.locator('[data-testid="staff-recent-toggle"]').check()
    await page.wait_for_timeout(600)
    csv_staff = [s for s in staff if s.get("import_source") == "csv_bulk"]
    body = await body_text()
    recent_count = extract_count("Retail Staff", body)
    expected_recent = f"{len(csv_staff)} of {staff_total}" if len(csv_staff) != staff_total else str(staff_total)
    assert recent_count == expected_recent, f"Recent CSV header expected {expected_recent}, got {recent_count}"
    code_to_staff = {s.get("staff_code"): s for s in staff if s.get("staff_code")}
    rows = [r for r in await table_rows("staff-list-tbody") if len(r) >= 4 and r[0].startswith("HL-")]
    assert rows, "Recent CSV filter produced no visible staff rows"
    non_csv_visible = [r[0] for r in rows if code_to_staff.get(r[0], {}).get("import_source") != "csv_bulk"]
    assert not non_csv_visible, f"Recent CSV filter showed non-csv rows: {non_csv_visible[:5]}"
    print(f"PASS staff recent toggle: header {recent_count}; all {len(rows)} visible rows have import_source=csv_bulk")

    # Live staff import to prove the post-import CTA exists and leads to discoverable rows.
    if await page.locator('[data-testid="staff-recent-toggle"]').is_checked():
        await page.locator('[data-testid="staff-recent-toggle"]').uncheck()
    await page.locator('[data-testid="staff-search-input"]').fill("")
    suffix = str(int(time.time()))[-5:]
    staff_phone_a = f"93046{suffix}"
    staff_phone_b = f"93047{suffix}"
    staff_brand = "BV46_STAFF_VERIFY_BRAND"
    staff_csv = OUT_DIR / "bug46_staff_import.csv"
    staff_csv.write_text(
        "Mob No,Name of Employee,Brand Name,Brand Category\n"
        f"{staff_phone_a},BV46 Staff Alpha,{staff_brand},Verification\n"
        f"{staff_phone_b},BV46 Staff Beta,{staff_brand},Verification\n",
        encoding="utf-8",
    )
    await upload_live("bulk-import-input", staff_csv, "staff bulk import")
    await expect_visible("import-result-banner", timeout=20000)
    await expect_visible("filter-recent-imports-btn", timeout=15000)
    await page.locator('[data-testid="filter-recent-imports-btn"]').click()
    await page.wait_for_timeout(1200)
    assert await page.locator('[data-testid="staff-recent-toggle"]').is_checked(), "Staff CTA did not enable Recent CSV imports toggle"
    post_staff_resp = await api_get("/admin/staff")
    post_staff = post_staff_resp["data"].get("staff", [])
    imported_staff = [s for s in post_staff if s.get("phone") in [staff_phone_a, staff_phone_b]]
    assert len(imported_staff) == 2, f"Expected 2 imported BV46 staff via API, got {imported_staff}"
    post_body = await body_text()
    assert "BV46 Staff Alpha" in post_body and "BV46 Staff Beta" in post_body and staff_brand in post_body, "Imported BV46 staff rows not visible after CTA"
    print("PASS staff post-import CTA: banner/CTA visible, CTA enabled recent filter, both imported rows visible")
    print("Evidence: staff Point 27 UI was visible after CTA (screenshot captured by MCP output).")

    # Point 28 — Coupon upload discoverability.
    await page.goto(f"{BASE_URL}/coupons", wait_until="domcontentloaded")
    await expect_visible("coupons-page")
    for tid in ["tab-inventory", "tab-all", "tab-issued"]:
        await expect_visible(tid)
    await page.locator('[data-testid="coupon-source-select"]').select_option("SRC_RWA")

    # Pre-clean exact BV46 codes if a prior interrupted run left available rows behind.
    pre_coupon_resp = await api_get("/admin/coupons/list?source_code=SRC_RWA&limit=5000")
    pre_coupons = pre_coupon_resp["data"].get("coupons", [])
    existing_bv46_ids = [c.get("id") for c in pre_coupons if c.get("brand_name") == "BV46_VERIFY_BRAND" and c.get("code") in ["BV46_A", "BV46_B"] and c.get("status") == "available"]
    if existing_bv46_ids:
        cleanup_pre = await api_post("/admin/coupons/delete", {"ids": existing_bv46_ids})
        print(f"Pre-cleaned existing available BV46 coupons: {cleanup_pre}")
        await page.locator('[data-testid="coupon-refresh-btn"]').click()
        await page.wait_for_timeout(1000)

    await page.locator('[data-testid="tab-all"]').click()
    await expect_visible("coupon-filter-bar")
    for tid in ["coupon-search-input", "coupon-brand-filter", "coupon-status-filter", "coupon-page-size"]:
        await expect_visible(tid)
    list_resp = await api_get("/admin/coupons/list?source_code=SRC_RWA&limit=5000")
    assert list_resp["ok"], f"GET coupons list failed: {list_resp}"
    all_coupon_count = len(list_resp["data"].get("coupons", []))
    await page.wait_for_function("(t) => document.body.innerText.includes(t)", arg=f"All Coupons · SRC_RWA ({all_coupon_count})", timeout=15000)
    print(f"PASS coupon All Coupons header count: {all_coupon_count} matches API list count")

    await page.locator('[data-testid="tab-inventory"]').click()
    await page.locator('[data-testid="coupon-upload-input"]').wait_for(state="attached", timeout=15000)
    print("PASS attached: coupon-upload-input")
    coupon_csv = OUT_DIR / "bug46_coupons.csv"
    coupon_csv.write_text(
        "Brand Name,Coupon Code,Coupon Value,Expiry Date\n"
        "BV46_VERIFY_BRAND,BV46_A,46,2026-12-31\n"
        "BV46_VERIFY_BRAND,BV46_B,46,2026-12-31\n",
        encoding="utf-8",
    )
    await upload_live("coupon-upload-input", coupon_csv, "coupon upload")
    await expect_visible("coupon-upload-result-banner", timeout=20000)
    await expect_visible("view-uploaded-coupons-btn", timeout=15000)
    upload_banner = await page.locator('[data-testid="coupon-upload-result-banner"]').inner_text()
    assert "2 imported" in upload_banner and "0 duplicates" in upload_banner and "0 invalid" in upload_banner, f"Unexpected coupon upload banner: {upload_banner}"
    await page.locator('[data-testid="view-uploaded-coupons-btn"]').click()
    await expect_visible("coupon-filter-bar")
    status_val = await page.locator('[data-testid="coupon-status-filter"]').input_value()
    assert status_val == "available", f"Show me the codes CTA did not apply available filter; got {status_val}"
    await page.wait_for_function("() => document.body.innerText.includes('BV46_A') && document.body.innerText.includes('BV46_B')", timeout=15000)
    coupon_body = await body_text()
    assert "BV46_VERIFY_BRAND" in coupon_body, "BV46 coupon brand missing after CTA"
    post_coupon_resp = await api_get("/admin/coupons/list?source_code=SRC_RWA&limit=5000")
    uploaded_coupons = [c for c in post_coupon_resp["data"].get("coupons", []) if c.get("brand_name") == "BV46_VERIFY_BRAND" and c.get("code") in ["BV46_A", "BV46_B"]]
    assert len(uploaded_coupons) == 2 and all(c.get("status") == "available" for c in uploaded_coupons), f"Uploaded coupons not present/available in API: {uploaded_coupons}"
    print("PASS coupon post-upload CTA: banner/CTA visible, All Coupons tab active, available filter applied, BV46_A/B visible")
    print("Evidence: coupons Point 28 UI was visible after CTA (screenshot captured by MCP output).")

    delete_ids = [c["id"] for c in uploaded_coupons]
    cleanup_coupon = await api_post("/admin/coupons/delete", {"ids": delete_ids})
    assert cleanup_coupon["ok"] and cleanup_coupon["data"].get("deleted") == 2, f"Coupon cleanup failed: {cleanup_coupon}"
    print("PASS cleanup: deleted 2 BV46_VERIFY_BRAND coupons via /api/admin/coupons/delete")

    result = {
        "base_url": BASE_URL,
        "staff_total_initial": staff_total,
        "staff_search_code": query,
        "staff_search_expected_matches": len(expected_matches),
        "staff_csv_bulk_count_initial": len(csv_staff),
        "staff_imported_phones": [staff_phone_a, staff_phone_b],
        "staff_imported_ids": [s.get("id") for s in imported_staff],
        "staff_imported_codes": [s.get("staff_code") for s in imported_staff],
        "coupon_all_count_initial": all_coupon_count,
        "coupon_uploaded_ids": delete_ids,
        "coupon_cleanup": cleanup_coupon,
        "verifications": [
            "staff-filter-bar/search/brand/recent/page-size present",
            "Retail Staff header matched GET /api/admin/staff total",
            "staff_code search narrowed table and header",
            "Recent CSV imports toggle showed only import_source=csv_bulk visible rows",
            "staff live import post-import CTA shown and made new rows visible",
            "coupon tabs Inventory/All Coupons/Issued present",
            "coupon-filter-bar/search/brand/status/page-size present",
            "All Coupons header matched GET /api/admin/coupons/list count",
            "coupon live upload post-upload CTA shown and made BV46_A/B visible with available filter",
        ],
    }
    (OUT_DIR / "bug46_ui_runtime_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print("OVERALL PASS bug46 preview discoverability verification")
except Exception as e:
    print(f"OVERALL FAIL bug46 preview discoverability verification: {type(e).__name__}: {e}")
    raise