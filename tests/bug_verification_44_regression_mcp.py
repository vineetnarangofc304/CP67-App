"""Light regression Playwright MCP script body for bug verification 44.

Focused on controls in the affected Staff Incentives page after the Point 27 UI
change: Add Staff dialog, QR PDF dialog, CSV template, Retailer Logins tab,
Slabs tab, and GET /api/admin/staff response shape.
"""

try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.goto("https://cp67-engage-preview.preview.emergentagent.com/login", wait_until="domcontentloaded")
    await page.evaluate("localStorage.clear()")
    await page.reload(wait_until="domcontentloaded")
    await page.locator('[data-testid="login-username-input"]').fill("admin")
    await page.locator('[data-testid="login-password-input"]').fill("CP67Admin@2025")
    await page.locator('[data-testid="login-submit-btn"]').click()
    await page.wait_for_timeout(1000)
    await page.goto("https://cp67-engage-preview.preview.emergentagent.com/staff-incentives", wait_until="domcontentloaded")
    await page.locator('[data-testid="staff-incentives-page"]').wait_for(timeout=20000)

    await page.locator('[data-testid="add-staff-btn"]').click()
    await page.locator('[data-testid="staff-form-name"]').wait_for(timeout=10000)
    assert await page.locator('[data-testid="staff-form-phone"]').is_visible()
    assert await page.locator('[data-testid="staff-form-brand"]').is_visible()
    await page.keyboard.press('Escape')

    await page.locator('[data-testid="qr-pdf-btn"]').click()
    await page.locator('[data-testid="qr-pdf-brand-select"]').wait_for(timeout=10000)
    assert await page.locator('[data-testid="qr-pdf-download-btn"]').is_visible()
    await page.keyboard.press('Escape')

    token = await page.evaluate("localStorage.getItem('cp67_token')")
    template = await page.evaluate("""async (token) => {
      const r = await fetch('/api/admin/staff/bulk-import/template.csv', {headers: {Authorization: `Bearer ${token}`}});
      const text = await r.text();
      return {status: r.status, text};
    }""", token)
    assert template['status'] == 200 and 'Mob No' in template['text'] and 'Brand Name' in template['text']

    await page.locator('[data-testid="tab-managers"]').click()
    await page.locator('[data-testid="managers-tbody"]').wait_for(timeout=10000)
    assert await page.locator('[data-testid="add-manager-btn"]').is_visible()

    await page.locator('[data-testid="tab-config"]').click()
    await page.locator('[data-testid="save-config-btn"]').wait_for(timeout=10000)
    assert await page.locator('[data-testid="brand-category-mapping-block"]').is_visible()

    shape = await page.evaluate("""async (token) => {
      const r = await fetch('/api/admin/staff', {headers: {Authorization: `Bearer ${token}`}});
      const d = await r.json();
      const sample = (d.staff || [])[0] || {};
      return {status: r.status, hasStaff: Array.isArray(d.staff), hasTotal: typeof d.total === 'number', sampleKeys: Object.keys(sample).sort()};
    }""", token)
    assert shape['status'] == 200 and shape['hasStaff'] and shape['hasTotal'] and 'staff_code' in shape['sampleKeys'] and 'brand_name' in shape['sampleKeys']
    print("BUG44_REGRESSION_VERDICT: PASS")
except Exception as e:
    print(f"BUG44_REGRESSION_VERDICT: FAIL - {type(e).__name__}: {e}")
    raise