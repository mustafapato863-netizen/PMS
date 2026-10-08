"""Read-only navigation QA. Requires a local Admin account via PMS_E2E_USERNAME/PMS_E2E_PASSWORD."""
import os
import re
import tempfile
from urllib.parse import urlsplit
from playwright.sync_api import expect, sync_playwright

base_url = os.environ.get("PMS_E2E_BASE_URL", "http://127.0.0.1:5173").rstrip("/")
if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise ValueError("This navigation test is restricted to a local development environment.")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base_url + "/login", wait_until="networkidle")
    page.get_by_label("Username", exact=True).fill(os.environ["PMS_E2E_USERNAME"])
    page.get_by_label("Password", exact=True).fill(os.environ["PMS_E2E_PASSWORD"])
    page.get_by_role("button", name="Sign In", exact=True).click()
    page.wait_for_url("**/executive**")
    page.goto(base_url + "/executive?period=2026-08", wait_until="networkidle")
    expect(page.get_by_role("complementary", name="Primary navigation")).to_be_visible()
    expect(page.get_by_role("navigation", name="Quick navigation")).to_have_count(0)
    for width, height in [(320, 740), (375, 812), (639, 704), (640, 704), (746, 704), (767, 704), (768, 900), (1024, 768), (844, 390)]:
        page.set_viewport_size({"width": width, "height": height})
        dock = page.get_by_role("navigation", name="Quick navigation")
        expect(dock).to_be_visible()
        assert dock.get_by_role("link").count() == (7 if width >= 640 else 3), f"Incorrect shortcut count at {width}px"
        if width >= 640:
            for label in ["Insights", "Planning", "Actions", "Account"]:
                expect(dock.get_by_role("link", name=f"Go to {label}", exact=True)).to_be_visible()
        else:
            expect(dock.get_by_role("link", name="Go to Insights", exact=True)).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Page overflow at {width}px"
        bounds = dock.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
        for item in dock.locator("a:visible, button:visible").all():
            box = item.bounding_box()
            assert box and box["width"] >= 44 and box["height"] >= 44
        menu = dock.get_by_role("button", name="Open full navigation")
        menu.click()
        dialog = page.get_by_role("dialog", name="Navigation menu")
        expect(dialog).to_be_visible()
        close = dialog.get_by_role("button", name="Close navigation sidebar")
        expect(close).to_be_focused()
        assert page.evaluate("document.body.style.overflow") == "hidden"
        assert page.locator("main").evaluate("el => el.inert")
        page.keyboard.press("Shift+Tab")
        expect(dialog.get_by_role("button", name="Log out", exact=True)).to_be_focused()
        page.keyboard.press("Tab")
        expect(close).to_be_focused()
        drawer = dialog.get_by_role("complementary")
        drawer_box = drawer.bounding_box()
        assert drawer_box and drawer_box["x"] >= 0 and drawer_box["x"] + drawer_box["width"] <= width
        page.screenshot(path=os.path.join(tempfile.gettempdir(), f"pms-navigation-drawer-{width}.png"))
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(menu).to_be_focused()
        assert page.evaluate("document.body.style.overflow") == ""
        page.screenshot(path=os.path.join(tempfile.gettempdir(), f"pms-navigation-dock-{width}.png"))
        print(f"PASS: {width}x{height}: dock/drawer fit; touch targets, focus trap, Escape and scroll lock work")

    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(base_url + "/function-summary/rcm?period=2026-08", wait_until="networkidle")
    expect(page.get_by_role("navigation", name="Quick navigation").get_by_role("link", name="Go to Planning")).to_be_visible()
    page.screenshot(path=os.path.join(tempfile.gettempdir(), "pms-navigation-expanded-tablet.png"))
    page.get_by_role("link", name="Go to Summary", exact=True).click()
    page.wait_for_url("**/executive**")
    expect(page.locator(".app-route-canvas").get_by_role("heading", name="Executive Summary", exact=True)).to_be_visible(timeout=30000)
    page.wait_for_load_state("networkidle")
    menu = page.get_by_role("button", name="Open full navigation")
    menu.click()
    expect(page.get_by_role("dialog", name="Navigation menu")).to_be_visible()
    try:
        page.get_by_role("dialog", name="Navigation menu").get_by_role("link", name="Account settings", exact=True).click(timeout=10000)
    except Exception:
        print(f"Navigation diagnostic: URL={page.url}, dialogs={page.get_by_role('dialog', name='Navigation menu').count()}, main inert={page.locator('main').evaluate('el => el.inert')}")
        page.screenshot(path=os.path.join(tempfile.gettempdir(), "pms-navigation-failure.png"))
        raise
    page.wait_for_url("**/account")
    expect(page.get_by_role("heading", name="Account settings", exact=True)).to_be_visible()
    expect(page.get_by_label("Full name", exact=True)).to_be_visible()
    expect(page.get_by_label("Username", exact=True)).to_have_attribute("readonly", "")
    for width in [320, 375, 640, 746, 768, 1024]:
        page.set_viewport_size({"width": width, "height": 900})
        expect(page.get_by_label("Full name", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Account page overflow at {width}px"
        page.screenshot(path=os.path.join(tempfile.gettempdir(), f"pms-account-{width}.png"))
    page.set_viewport_size({"width": 768, "height": 900})
    print("PASS: Account opens personal settings, with no overflow from 320px through tablet")
    expect(page.get_by_role("dialog", name="Navigation menu")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Quick navigation")).to_be_visible()
    page.go_back(wait_until="networkidle")
    menu.click()
    page.go_back(wait_until="networkidle")
    expect(page.get_by_role("dialog", name="Navigation menu")).to_have_count(0)
    page.go_forward(wait_until="networkidle")
    expect(page.get_by_role("dialog", name="Navigation menu")).to_have_count(0)
    print("PASS: browser Back/Forward does not reopen a previously opened drawer")
    page.get_by_role("button", name="Open user menu").click()
    expect(page.get_by_role("menu", name="User menu")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Tablet header overflow"
    page.mouse.click(5, 25)
    expect(page.get_by_role("menu", name="User menu")).to_have_count(0)
    page.get_by_role("button", name=re.compile("Switch to (dark|light) mode")).click()
    page.screenshot(path=os.path.join(tempfile.gettempdir(), "pms-navigation-dark-tablet.png"))
    page.emulate_media(reduced_motion="reduce")
    menu.click()
    assert page.locator(".app-sidebar").evaluate("el => getComputedStyle(el).transitionDuration") == "0s"
    page.keyboard.press("Escape")
    menu.click()
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(page.get_by_role("dialog", name="Navigation menu")).to_have_count(0)
    assert page.evaluate("document.body.style.overflow") == ""
    page.set_viewport_size({"width": 375, "height": 812})
    expect(page.get_by_role("dialog", name="Navigation menu")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Quick navigation")).to_be_visible()
    page.set_viewport_size({"width": 1440, "height": 900})
    expect(page.get_by_role("navigation", name="Quick navigation")).to_have_count(0)
    expect(page.get_by_role("complementary", name="Primary navigation")).to_be_visible()
    page.get_by_role("button", name="Minimize navigation sidebar").click()
    expect(page.locator(".app-sidebar")).to_have_class(re.compile("is-collapsed"))
    page.get_by_role("button", name="Expand navigation sidebar").click()
    page.get_by_role("button", name="Log out", exact=True).click()
    assert not errors, errors
    print("PASS: route navigation closes drawer; tablet header fits; dark/reduced motion and desktop collapse preserved")
    browser.close()
