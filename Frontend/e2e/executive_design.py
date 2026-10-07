"""Read-only local checks and screenshots for the executive hero/function cards."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def run():
    base = os.environ.get("PMS_E2E_URL", "http://127.0.0.1:5173")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Local testing only"
    artifacts = Path(__file__).parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, reduced_motion="reduce")
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        page.get_by_label("Username", exact=True).fill(os.environ["PMS_E2E_USERNAME"])
        page.get_by_label("Password", exact=True).fill(os.environ["PMS_E2E_PASSWORD"])
        page.get_by_role("button", name="Sign In", exact=True).click()
        page.wait_for_url(re.compile(r"/executive(?:\?|$)"))
        hero = page.locator('[aria-labelledby="exec-hero-title"]')
        functions = page.locator('[aria-labelledby="exec-functions-title"]')
        expect(hero).to_be_visible(timeout=60_000)
        expect(functions.locator("article").first).to_be_visible(timeout=60_000)
        page.wait_for_load_state("networkidle")
        for width in [1440, 1024, 768, 390]:
            page.set_viewport_size({"width": width, "height": 1050})
            page.wait_for_timeout(250)  # ResizeObserver, not an application/network readiness wait.
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Overflow at {width}px"
            for surface in [hero, functions]:
                assert surface.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), f"Card overflow at {width}px"
            for card in functions.locator("article").all():
                chart = card.get_by_test_id("function-trend-chart")
                expect(chart).to_be_visible()
                labels = card.get_by_test_id("function-trend-value")
                assert labels.count() == chart.get_by_test_id("function-trend-point").count()
                bounds = card.bounding_box()
                for label in labels.all():
                    box = label.bounding_box()
                    assert box["x"] >= bounds["x"] and box["x"] + box["width"] <= bounds["x"] + bounds["width"] + 1
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(artifacts / f"executive-design-{width}.png"), full_page=True)
            checks.append(f"Hero and function cards fit {width}px; all measured scores are labelled")
        page.set_viewport_size({"width": 1440, "height": 1050})
        for surface in [hero]:
            point = surface.locator('g[role="img"][tabindex="0"]').first
            point.focus()
            tooltip = surface.get_by_test_id("executive-trend-tooltip")
            expect(tooltip).to_be_visible()
            assert "%" in tooltip.inner_text()
            point.press("ArrowLeft")
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            expect(tooltip).not_to_be_visible()
        checks.append("Hero chart retains keyboard navigation and percentage tooltips")
        for chart in functions.get_by_test_id("function-trend-chart").all():
            markup = chart.inner_html()
            assert chart.get_attribute("pointer-events") == "none"
            assert chart.locator("[tabindex], animate, animateTransform, title").count() == 0
            chart.scroll_into_view_if_needed()
            box = chart.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            expect(page.get_by_test_id("executive-trend-tooltip")).to_have_count(0)
            assert chart.inner_html() == markup
        checks.append("Function charts are static: visible score labels, no hover tooltip, animation or focus handlers")
        for mode in ["dark", "light"]:
            page.get_by_role("button", name=f"Switch to {mode} mode", exact=True).first.click()
            expect(page.get_by_role("button", name=f"Switch to {'light' if mode == 'dark' else 'dark'} mode").first).to_be_visible()
            page.wait_for_timeout(250)
            hero.screenshot(path=str(artifacts / f"executive-hero-{mode}.png"))
            functions.screenshot(path=str(artifacts / f"executive-functions-{mode}.png"))
            page.set_viewport_size({"width": 390, "height": 1050})
            page.wait_for_timeout(250)
            hero.screenshot(path=str(artifacts / f"executive-hero-mobile-{mode}.png"))
            functions.locator("article").first.screenshot(path=str(artifacts / f"executive-function-mobile-{mode}.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.set_viewport_size({"width": 1440, "height": 1050})
            checks.append(f"{mode.title()} theme works on desktop and mobile")
        print(json.dumps({"checks": checks, "errors": errors}, indent=2))
        assert not errors
        browser.close()


if __name__ == "__main__":
    run()
