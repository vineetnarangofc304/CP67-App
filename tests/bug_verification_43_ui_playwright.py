"""Reference Playwright actions used by browser automation for Point 26 UI verification.

The same actions were submitted to the MCP browser automation runner against the
preview frontend. Core assertions:
- admin can log in and open /coupons
- a 6-row CSV uploaded through the UI as a live import shows 2 imported / 4 invalid
- inventory table for the isolated source shows exactly the two valid brand rows
  and excludes compact ISO, week-date, garbage, and empty-expiry rows
"""

PLAYWRIGHT_ACTIONS = r'''
import json
from pathlib import Path

try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    ctx = json.loads(Path("/app/test_reports/bug_verification_43_ui_context.json").read_text())
    source = ctx["source"]
    csv_path = ctx["csv_path"]

    async def handle_dialog(dialog):
        print(f"Dialog seen: {dialog.message}")
        await dialog.dismiss()  # Cancel = live import in this UI
    page.on("dialog", lambda dialog: __import__("asyncio").create_task(handle_dialog(dialog)))

    await page.evaluate("localStorage.removeItem('cp67_token')")
    await page.goto("http://localhost:3000/login", wait_until="domcontentloaded")
    await page.locator('[data-testid="login-username-input"]').fill("admin")
    await page.locator('[data-testid="login-password-input"]').fill("CP67Admin@2025")
    await page.locator('[data-testid="login-submit-btn"]').click()
    await page.wait_for_timeout(1500)
    print("Login submitted")

    await page.goto("http://localhost:3000/coupons", wait_until="domcontentloaded")
    await page.locator('[data-testid="coupons-page"]').wait_for(timeout=15000)
    print("Coupons page loaded")

    await page.evaluate('''(src) => {
      const sel = document.querySelector('[data-testid="coupon-source-select"]');
      const opt = document.createElement('option');
      opt.value = src;
      opt.textContent = src;
      sel.appendChild(opt);
      sel.value = src;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }''', source)
    await page.wait_for_timeout(1000)
    print(f"Injected isolated source option: {source}")

    await page.locator('[data-testid="coupon-upload-input"]').set_input_files(csv_path)
    await page.locator('[data-testid="coupon-upload-result-banner"]').wait_for(timeout=20000)
    banner = await page.locator('[data-testid="coupon-upload-result-banner"]').inner_text()
    print(f"Upload banner: {banner}")
    assert "2 imported" in banner and "4 invalid" in banner, banner

    await page.wait_for_timeout(1500)
    tbody = page.locator('[data-testid="coupon-inventory-tbody"]')
    table_text = await tbody.inner_text()
    rows = await tbody.locator('tr').count()
    print(f"Inventory rows={rows}; table={table_text}")
    assert rows == 2, f"Expected exactly 2 inventory rows, got {rows}: {table_text}"
    for brand in ctx["valid_brands"]:
        assert brand in table_text, f"Valid brand missing from inventory table: {brand}"
    for brand in ctx["invalid_brands"]:
        assert brand not in table_text, f"Invalid brand unexpectedly present in inventory table: {brand}"

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*=\"error\"], [id*=\"error\"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print("UI coupon strict upload verification passed")
except Exception as e:
    print(f"UI coupon strict upload verification failed: {e}")
    raise
'''