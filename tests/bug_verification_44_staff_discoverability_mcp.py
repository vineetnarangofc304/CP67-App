"""Playwright MCP script body used for bug verification 44.

Focused scope: Point 27 imported staff discoverability on /staff-incentives.
This file is kept as the test artifact; the same body was run via the browser
automation tool in the preview environment.
"""

# Executed inside the MCP browser runner's async function with `page` available.
import re

try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    print("Step 1: viewport set")
    page.on("dialog", lambda dialog: dialog.dismiss())

    await page.goto("https://cp67-engage-preview.preview.emergentagent.com/login", wait_until="domcontentloaded")
    await page.locator('[data-testid="login-username-input"]').fill("admin")
    await page.locator('[data-testid="login-password-input"]').fill("CP67Admin@2025")
    await page.locator('[data-testid="login-submit-btn"]').click()
    await page.wait_for_timeout(1000)
    await page.goto("https://cp67-engage-preview.preview.emergentagent.com/staff-incentives", wait_until="domcontentloaded")
    await page.locator('[data-testid="staff-incentives-page"]').wait_for(timeout=20000)
    print("Step 2: logged in and opened staff incentives")

    token = await page.evaluate("localStorage.getItem('cp67_token')")
    api_data = await page.evaluate("""async (token) => {
      const r = await fetch('/api/admin/staff', {headers: {Authorization: `Bearer ${token}`}});
      return await r.json();
    }""", token)
    total = len(api_data.get('staff', []))
    csv_codes = {s.get('staff_code') for s in api_data.get('staff', []) if s.get('import_source') == 'csv_bulk'}
    csv_count = len(csv_codes)
    print(f"Step 3: API staff total={total}, csv_bulk={csv_count}")

    header = await page.locator('text=/Retail Staff \\([0-9]+/').first.text_content()
    assert f"Retail Staff ({total})" in header, f"Header mismatch: {header} vs API total {total}"
    for testid in ['staff-filter-bar', 'staff-search-input', 'staff-brand-filter', 'staff-recent-toggle', 'staff-page-size']:
        assert await page.locator(f'[data-testid="{testid}"]').is_visible(), f"Missing {testid}"
    assert await page.locator('[data-testid="staff-truncated-hint"]').is_visible(), "Default truncation hint missing"
    print("Step 4: header, filter bar controls, truncation hint verified")

    await page.locator('[data-testid="staff-search-input"]').fill("HL-0757")
    await page.wait_for_timeout(500)
    header = await page.locator('text=/Retail Staff \\([0-9]+/').first.text_content()
    assert f"Retail Staff (1 of {total})" in header, f"Search header mismatch: {header}"
    tbody = await page.locator('[data-testid="staff-list-tbody"]').inner_text()
    assert "HL-0757" in tbody and "TEST_OtherBrand_Emp" in tbody, "Search result row missing"
    print("Step 5: search by staff_code filters to matching row")

    await page.locator('[data-testid="staff-search-input"]').fill("")
    await page.locator('[data-testid="staff-brand-filter"]').select_option("Lifestyle & Homecentre")
    await page.wait_for_timeout(500)
    brand_rows = await page.locator('[data-testid="staff-list-tbody"] tr').count()
    visible_brands = await page.evaluate("""() => Array.from(document.querySelectorAll('[data-testid="staff-list-tbody"] tr')).map(tr => tr.cells[2]?.textContent?.trim()).filter(Boolean)""")
    assert brand_rows > 0, "Brand filter returned no visible rows"
    assert all(b == "Lifestyle & Homecentre" for b in visible_brands), f"Brand filter leaked other brands: {visible_brands[:5]}"
    print(f"Step 6: brand filter visible rows are all Lifestyle & Homecentre ({brand_rows} rows shown)")

    await page.locator('[data-testid="staff-brand-filter"]').select_option("")
    await page.locator('[data-testid="staff-recent-toggle"]').check()
    await page.wait_for_timeout(700)
    header = await page.locator('text=/Retail Staff \\([0-9]+/').first.text_content()
    assert f"Retail Staff ({csv_count} of {total})" in header, f"Recent toggle header mismatch: {header} expected csv_count={csv_count} total={total}"
    visible_codes = await page.evaluate("""() => Array.from(document.querySelectorAll('[data-testid="staff-list-tbody"] tr')).map(tr => tr.cells[0]?.textContent?.trim()).filter(Boolean)""")
    assert visible_codes and all(c in csv_codes for c in visible_codes), f"Recent filter visible rows include non csv_bulk codes: {visible_codes[:10]}"
    await page.locator('[data-testid="staff-recent-toggle"]').uncheck()
    print("Step 7: recent CSV imports filter verified against API import_source values")

    await page.locator('[data-testid="bulk-import-input"]').set_input_files('/app/tests/bug44_staff_import.csv')
    await page.locator('[data-testid="import-result-banner"]').wait_for(timeout=30000)
    banner = await page.locator('[data-testid="import-result-banner"]').inner_text()
    assert '2 imported' in banner and '0 invalid' in banner, f"Unexpected import banner: {banner}"
    assert await page.locator('[data-testid="import-view-hint"]').is_visible(), "Post-import view hint missing"
    await page.locator('[data-testid="filter-recent-imports-btn"]').click()
    await page.wait_for_timeout(1000)
    assert await page.locator('[data-testid="staff-recent-toggle"]').is_checked(), "CTA did not enable recent toggle"
    tbody = await page.locator('[data-testid="staff-list-tbody"]').inner_text()
    assert 'BV44 Staff One' in tbody and 'BV44 Staff Two' in tbody and 'BV44_TEST_BRAND' in tbody, "Imported test rows not visible after CTA"
    print("Step 8: live CSV import banner, hint, CTA, and newly imported rows visible")

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print("BUG44_UI_VERDICT: PASS")
except Exception as e:
    print(f"BUG44_UI_VERDICT: FAIL - {type(e).__name__}: {e}")
    raise