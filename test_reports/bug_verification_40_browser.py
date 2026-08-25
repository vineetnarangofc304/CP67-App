# This file mirrors the Playwright script submitted to mcp_browser_automation.
# It is intentionally written as a snippet run inside an async function with a
# provided `page` object.

import asyncio

BASE_URL = 'https://mall-engagement-hub.preview.emergentagent.com'
STAFF_CSV = '/app/test_reports/ui_staff_import_40.csv'
MAPPING_CSV = '/app/test_reports/ui_mapping_40.csv'

async def print_errors(label):
    error_text = await page.evaluate("""() => {
      const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
      return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"{label}: Found error message: {error_text}")
    else:
        print(f"{label}: No error messages found on the page")
    return error_text

async def screen_text():
    return await page.locator('body').inner_text(timeout=5000)

async def assert_no_invalid_token(label):
    txt = await screen_text()
    assert 'Invalid token' not in txt, f'{label}: raw Invalid token is visible on screen: {txt[:500]}'
    await print_errors(label)

async def login_admin():
    await page.goto(f'{BASE_URL}/login', wait_until='domcontentloaded')
    await page.locator('[data-testid="login-username-input"]').fill('admin')
    await page.locator('[data-testid="login-password-input"]').fill('CP67Admin@2025')
    await page.locator('[data-testid="login-submit-btn"]').click()
    await page.wait_for_timeout(1200)
    await page.goto(f'{BASE_URL}/staff-incentives', wait_until='domcontentloaded')
    await page.locator('[data-testid="staff-incentives-page"]').wait_for(timeout=15000)
    print('PASS: admin login and Staff Incentives page loaded')

async def patch_fetch_401(substr):
    await page.evaluate("""(substr) => {
      window.__originalFetchForBugTest = window.__originalFetchForBugTest || window.fetch.bind(window);
      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes(substr)) {
          return new Response(JSON.stringify({ detail: 'Invalid token' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return window.__originalFetchForBugTest(input, init);
      };
    }""", substr)

async def assert_session_expired_redirect(label):
    await page.get_by_text('Session expired', exact=False).wait_for(timeout=3000)
    await assert_no_invalid_token(label)
    await page.wait_for_timeout(1200)
    assert '/login' in page.url or page.url.rstrip('/') == BASE_URL, f'{label}: expected login redirect, got {page.url}'
    await page.locator('[data-testid="login-username-input"]').wait_for(timeout=8000)
    print(f'PASS: {label} shows friendly session-expired toast and redirects to login')

try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.goto(BASE_URL, wait_until='domcontentloaded')
    await page.evaluate("localStorage.clear()")
    print('PASS: browser state cleared')

    # Point 5 admin screen + regression Add Staff field.
    await login_admin()
    await page.locator('[data-testid="tab-managers"]').click()
    await page.locator('[data-testid="copy-portal-url-btn"]').wait_for(timeout=10000)
    await page.locator('[data-testid="open-portal-btn"]').wait_for(timeout=10000)
    await page.get_by_text('9100011122', exact=False).wait_for(timeout=10000)
    invite_count = await page.locator('[data-testid^="mgr-invite-"]').count()
    assert invite_count >= 1, 'Retailer Logins tab has no WhatsApp Invite button rows'
    print(f'PASS: Retailer Logins tab has Copy URL, Open Portal, and {invite_count} WhatsApp Invite button(s)')

    await page.locator('[data-testid="tab-staff"]').click()
    await page.locator('[data-testid="add-staff-btn"]').click()
    await page.locator('[data-testid="staff-form-brand-category"]').wait_for(timeout=5000)
    print('PASS: Add Staff dialog exposes Brand Category input')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(300)

    # Point 6(a): bad token on reload redirects without raw Invalid token.
    await page.evaluate("localStorage.setItem('cp67_token', 'garbage.jwt')")
    await page.reload(wait_until='domcontentloaded')
    await page.locator('[data-testid="login-username-input"]').wait_for(timeout=10000)
    await assert_no_invalid_token('bad token reload')
    print('PASS: garbage cp67_token reload redirects to login without raw Invalid token text')

    # Point 6(b-d): force 401 on each relevant admin action.
    await login_admin()
    await patch_fetch_401('admin/staff/bulk-import')
    page.once('dialog', lambda dialog: asyncio.create_task(dialog.dismiss()))
    await page.locator('[data-testid="bulk-import-input"]').set_input_files(STAFF_CSV)
    await assert_session_expired_redirect('Staff Bulk Import CSV 401')

    await login_admin()
    await patch_fetch_401('bulk-import/template.csv')
    await page.locator('[data-testid="download-template-btn"]').click()
    await assert_session_expired_redirect('Staff Template 401')

    await login_admin()
    await page.locator('[data-testid="tab-config"]').click()
    await page.locator('[data-testid="mapping-template-btn"]').wait_for(timeout=10000)
    await patch_fetch_401('brand-category-mapping/template.csv')
    await page.locator('[data-testid="mapping-template-btn"]').click()
    await assert_session_expired_redirect('Slabs Mapping Template 401')

    await login_admin()
    await page.locator('[data-testid="tab-config"]').click()
    await page.locator('[data-testid="mapping-upload-input"]').wait_for(state='attached', timeout=10000)
    await patch_fetch_401('brand-category-mapping')
    page.once('dialog', lambda dialog: asyncio.create_task(dialog.dismiss()))
    await page.locator('[data-testid="mapping-upload-input"]').set_input_files(MAPPING_CSV)
    await assert_session_expired_redirect('Slabs Upload Mapping CSV 401')

    # Point 7 UI dropdowns, mapping template, and live mapping upload.
    await login_admin()
    await page.locator('[data-testid="tab-config"]').click()
    cat_select = page.locator('[data-testid="override-new-key-category_slabs"]')
    brand_select = page.locator('[data-testid="override-new-key-brand_slabs"]')
    await cat_select.wait_for(timeout=15000)
    await brand_select.wait_for(timeout=15000)
    await page.wait_for_timeout(500)
    cat_options = await cat_select.locator('option').all_inner_texts()
    brand_options = await brand_select.locator('option').all_inner_texts()
    cat_real = [x for x in cat_options if x and not x.startswith('Pick') and not x.startswith('All (')]
    brand_real = [x for x in brand_options if x and not x.startswith('Pick')]
    assert len(cat_real) >= 15, f'expected >=15 category options, got {len(cat_real)}: {cat_options[:20]}'
    assert any(x == 'Fashion' for x in cat_real), f'Fashion missing from categories: {cat_options[:30]}'
    assert any(x == 'Electronics' for x in cat_real), f'Electronics missing from categories: {cat_options[:30]}'
    assert any('food' in x.lower() and 'beverage' in x.lower() for x in cat_real), f'Food & Beverage missing from categories: {cat_options[:30]}'
    assert any(x.startswith('All (categories & brands)') for x in cat_options), f'All option missing from category select: {cat_options[:10]}'
    assert len(brand_real) >= 100, f'expected >=100 brand options, got {len(brand_real)}'
    for expected in ['Zara', 'Adidas', 'Apple']:
        assert expected in brand_real, f'{expected} missing from brand select'
    print(f'PASS: Slab dropdowns populated with {len(cat_real)} categories, All option, and {len(brand_real)} brands')

    async with page.expect_download() as download_info:
        await page.locator('[data-testid="mapping-template-btn"]').click()
    download = await download_info.value
    assert 'brand-category-mapping-template' in download.suggested_filename, f'unexpected mapping template filename {download.suggested_filename}'
    print(f'PASS: mapping template button downloads {download.suggested_filename}')

    page.once('dialog', lambda dialog: asyncio.create_task(dialog.dismiss()))
    await page.locator('[data-testid="mapping-upload-input"]').set_input_files(MAPPING_CSV)
    await page.get_by_text('Mapping applied', exact=False).wait_for(timeout=10000)
    print('PASS: live brand-category mapping upload shows success toast')

    await page.reload(wait_until='domcontentloaded')
    await page.locator('[data-testid="tab-config"]').click()
    await brand_select.wait_for(timeout=15000)
    await page.wait_for_timeout(700)
    brand_options_after = await page.locator('[data-testid="override-new-key-brand_slabs"]').locator('option').all_inner_texts()
    assert 'TEST_BUG_BRAND_XYZ' in brand_options_after, 'uploaded TEST_BUG_BRAND_XYZ not visible in brand slab dropdown after refresh'
    print('PASS: uploaded test brand appears in Brand-wise Slabs dropdown after refresh')

    # Retailer portal E2E.
    await page.goto(f'{BASE_URL}/staff-app/retailer/login', wait_until='domcontentloaded')
    await page.locator('[data-testid="retailer-phone-input"]').fill('9100011122')
    await page.locator('[data-testid="retailer-send-otp-btn"]').click()
    await page.locator('[data-testid="retailer-otp-0"]').wait_for(timeout=10000)
    await page.locator('[data-testid="retailer-otp-0"]').fill('1234')
    await page.locator('[data-testid="retailer-verify-otp-btn"]').click()
    await page.locator('[data-testid="retailer-dashboard"]').wait_for(timeout=15000)
    dash_txt = await page.locator('[data-testid="retailer-dashboard"]').inner_text()
    for label in ['Redeemable', 'Redeemed', 'Pending', 'Active Staff', 'Staff Incentives']:
        assert label in dash_txt, f'retailer dashboard missing {label}'
    assert 'customer_phone' not in dash_txt and 'bill_image' not in dash_txt and 'bill_id' not in dash_txt, 'retailer dashboard visible text includes forbidden PII-like field names'
    print('PASS: retailer portal OTP login lands on dashboard with summary tiles and no visible PII field names')

    print('BROWSER_VERIFICATION_STATUS: passed')
except Exception as exc:
    print(f'BROWSER_VERIFICATION_STATUS: failed: {exc}')
    await page.screenshot(path='/app/test_reports/browser_iteration_40_failure.jpeg', quality=40, full_page=False)
    raise