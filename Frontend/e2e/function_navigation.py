"""Read-only local regression: both summary columns open the target sheet."""
import json
import os
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


def run():
    base = os.environ.get("PMS_E2E_URL", "http://127.0.0.1:5173")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Local testing only"
    checks = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        page.get_by_label("Username", exact=True).fill(os.environ["PMS_E2E_USERNAME"])
        page.get_by_label("Password", exact=True).fill(os.environ["PMS_E2E_PASSWORD"])
        page.get_by_role("button", name="Sign In", exact=True).click()
        page.wait_for_url("**/executive**")
        for surface in ["Team leaderboard", "Roles needing attention"]:
            page.goto(base + "/function-summary/marketing?period=2026-08&region=EGY&level=Employee")
            page.wait_for_load_state("networkidle")
            card = page.get_by_role("region", name=surface, exact=True)
            link = card.get_by_role("link", name="Media Buyer", exact=True)
            expect(link).to_be_visible(timeout=60_000)
            link.click()
            page.wait_for_url("**/team/marketing?**")
            expect(page.get_by_role("heading", name="Media Buyer · Employee", exact=True)).to_be_visible(timeout=60_000)
            expect(page.get_by_role("heading", name="Media Buyer KPIs", exact=True)).to_be_visible()
            query = parse_qs(urlparse(page.url).query)
            assert query["position_view"] == ["Media Buyer"]
            assert query["month"] == ["August"] and query["year"] == ["2026"]
            assert query["region"] == ["EGY"]
            checks.append(surface + " opens Media Buyer employee sheet with KPIs and the selected period/region")
        page.goto(base + "/function-summary/rcm?period=2026-06&region=UAE&branch=dubai&level=Employee")
        page.wait_for_load_state("networkidle")
        card = page.get_by_role("region", name="Team leaderboard", exact=True)
        link = card.get_by_role("link", name="Coding", exact=True)
        expect(link).to_be_visible(timeout=60_000)
        link.click()
        page.wait_for_url("**/team/coding?**")
        expect(page.get_by_role("heading", name="Coding", exact=True)).to_be_visible(timeout=60_000)
        query = parse_qs(urlparse(page.url).query)
        assert query["branch"] == ["dubai"] and query["region"] == ["UAE"]
        assert query["month"] == ["June"] and query["year"] == ["2026"]
        checks.append("RCM leaderboard opens Coding dashboard with the selected month, branch and region")
        assert not errors, "Unexpected browser exception"
        print(json.dumps({"checks": checks, "browser_error_count": len(errors)}, indent=2))
        page.get_by_role("button", name="Log out", exact=True).click()
        expect(page.get_by_label("Username", exact=True)).to_be_visible()
        browser.close()


if __name__ == "__main__":
    run()
