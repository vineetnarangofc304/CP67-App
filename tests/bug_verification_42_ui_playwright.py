"""Reference Playwright actions used by browser automation for Point 26 UI verification.

This file is intentionally not executed directly by pytest; the same actions were
submitted to the MCP browser automation runner against the preview frontend.
"""

# See bug_verification_42 UI run in the browser automation logs. Core assertions:
# - admin can log in and open /coupons
# - live CSV upload dismisses the confirm dialog (Cancel = live import)
# - toast/banner show 2 imported and 2 invalid
# - inventory refresh shows exactly the two valid brands and excludes invalid brands