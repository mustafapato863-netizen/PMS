"""Read-only local regression: user actions stay inside the viewport."""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def run():
    base = os.environ.get("PMS_E2E_URL", "http://127.0.0.1:5173")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Local testing only"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 600})
        page.goto(base + "/login")
        page.get_by_label("Username", exact=True).fill(os.environ["PMS_E2E_USERNAME"])
        page.get_by_label("Password", exact=True).fill(os.environ["PMS_E2E_PASSWORD"])
        page.get_by_role("button", name="Sign In", exact=True).click()
        page.wait_for_url("**/executive**")
        page.goto(base + "/settings?section=users")
        page.get_by_role("button", name="User Management", exact=False).click()
        for viewport in [{"width": 1440, "height": 600}, {"width": 390, "height": 700}, {"width": 844, "height": 390}]:
            page.set_viewport_size(viewport)
            trigger = page.get_by_role("button", name="Actions for").last
            expect(trigger).to_be_visible(timeout=30_000)
            trigger.scroll_into_view_if_needed()
            trigger.click()
            menu = page.get_by_role("group", name="User actions", exact=True)
            expect(menu).to_be_visible()
            bounds = menu.bounding_box()
            print(json.dumps({"menu_bounds": bounds, "viewport": viewport}))
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= viewport["height"], "Last-row user menu is clipped below the viewport"
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= viewport["width"], "User menu is clipped horizontally"
            for name in ["Edit", "Disable", "Delete"]:
                expect(menu.get_by_role("button", name=name, exact=True)).to_be_in_viewport()
            page.keyboard.press("Escape")
            expect(menu).not_to_be_visible()
            expect(trigger).to_be_focused()
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.get_by_role("button", name="Add user", exact=True).click()
        dialog = page.get_by_role("dialog", name="Add user", exact=True)
        dialog.get_by_role("combobox", name="Role", exact=True).select_option("Function Director")
        for name in ["Sales", "CSR", "Pharmacy"]:
            checkbox = dialog.get_by_role("checkbox", name=name, exact=True)
            expect(checkbox).to_be_visible()
            checkbox.check()
            expect(checkbox).to_be_checked()
        expect(dialog.get_by_role("checkbox", name="RCM", exact=True)).not_to_be_checked()
        # Cancel the draft; never create or alter a real account during this smoke.
        dialog.get_by_role("button", name="Cancel", exact=True).click()
        expect(dialog).not_to_be_visible()
        print("PASS: standalone function choices visible and isolated; draft cancelled")
        page.get_by_role("button", name="Log out", exact=True).click()
        expect(page.get_by_label("Username", exact=True)).to_be_visible()
        browser.close()


if __name__ == "__main__":
    run()
