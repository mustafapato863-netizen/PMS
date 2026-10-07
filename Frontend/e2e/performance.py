"""Read-only local browser checks. Credentials are supplied through environment variables.

Run: python e2e/performance.py --report baseline
Requires the local frontend/backend and Python Playwright with Chromium installed.
Never writes users, performance data, actions, or configuration.
"""
import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from playwright.sync_api import expect, sync_playwright


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="latest")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    base = os.environ.get("PMS_E2E_URL", "http://127.0.0.1:5173")
    assert urlparse(base).hostname in {"localhost", "127.0.0.1"}, "Local testing only"
    username = os.environ["PMS_E2E_USERNAME"]
    password = os.environ["PMS_E2E_PASSWORD"]
    result = {"environment": "local Vite development server", "checks": [], "requests": [], "errors": []}
    started = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.on("pageerror", lambda error: result["errors"].append(str(error)))
        page.on("request", lambda request: started.update({request: time.perf_counter()}))

        def response_received(response):
            path = urlparse(response.url).path
            if path.startswith("/api/") and "/auth/" not in path:
                result["requests"].append({"path": path, "status": response.status,
                    "ms": round((time.perf_counter() - started.get(response.request, time.perf_counter())) * 1000),
                    "cursor_page": any(key == "cursor" for key, _ in parse_qsl(urlparse(response.url).query)),
                    "query": urlencode([(key, value) for key, value in parse_qsl(urlparse(response.url).query) if key != "cursor"])})

        page.on("response", response_received)
        page.goto(base + "/login")
        page.wait_for_load_state("networkidle")
        page.get_by_label("Username", exact=True).fill(username)
        page.get_by_label("Password", exact=True).fill(password)
        begin = time.perf_counter()
        page.get_by_role("button", name="Sign In", exact=True).click()
        page.wait_for_url(re.compile(r"/executive(?:\?|$)"))
        roster = page.locator('[aria-labelledby="exec-employees-below-title"]')
        expect(roster.locator("li").first).to_be_visible(timeout=60_000)
        result["cold_login_to_roster_ms"] = round((time.perf_counter() - begin) * 1000)
        page.wait_for_load_state("networkidle")
        result["checks"].append("Login and Executive roster loaded")
        if args.inspect:
            print(json.dumps({"buttons": page.get_by_role("button").evaluate_all("els => els.map(e => e.getAttribute('aria-label') || e.innerText).filter(Boolean)"),
                "links": page.locator("aside a").evaluate_all("els => els.map(e => ({label:e.innerText, href:e.getAttribute('href')}))"),
                "metrics": result}, indent=2))
        else:
            assert roster.locator("li").count() == 8, "Roster must show eight employees"
            result["checks"].append("Roster has eight employees per page")
            def roster_request_count():
                return len([request for request in result["requests"] if request["path"] == "/api/performance/records" and "score_lt=90" in request["query"]])

            request_count = roster_request_count()
            begin = time.perf_counter()
            roster.get_by_role("button", name="Next page", exact=True).click()
            expect(roster.get_by_text(re.compile(r"Page 2 of"))).to_be_visible()
            assert roster.locator("li").count() == 8
            result["cached_roster_next_page_ms"] = round((time.perf_counter() - begin) * 1000)
            assert roster_request_count() == request_count, "Pagination must use cached data"
            result["checks"].append("Next page is cached without additional API requests")
            roster.get_by_role("button", name="Previous page", exact=True).click()
            expect(roster.get_by_text(re.compile(r"Page 1 of"))).to_be_visible()
            result["checks"].append("Previous page uses cached data")
            show_teams = page.get_by_role("button", name="Show all teams", exact=True)
            show_teams.click()
            expect(page.get_by_role("table", name="All teams", exact=True)).to_be_visible()
            assert urlparse(page.url).path == "/executive"
            page.get_by_role("button", name="Show at-risk teams", exact=True).click()
            result["checks"].append("Show all teams expands inline and can collapse")

            def open_filters():
                page.get_by_role("button", name=re.compile(r"^Executive filters[.,]")).click()
                dialog = page.get_by_role("dialog", name="Executive filters", exact=True)
                expect(dialog).to_be_visible()
                return dialog

            dialog = open_filters()
            dialog.get_by_role("button", name="Team", exact=True).click()
            page.get_by_role("listbox", name="Team", exact=True).get_by_role("option", name="Coding", exact=True).click()
            expect(dialog.get_by_role("button", name="Function", exact=True)).to_contain_text("RCM")
            expect(page).to_have_url(re.compile(r"function=RCM.*team=Coding"))
            dialog.get_by_role("button", name="Done", exact=True).click()
            expect(roster.locator("li").first).to_be_visible()
            result["checks"].append("Team selection automatically selects its function")
            dialog = open_filters()
            dialog.get_by_role("button", name="Performance level", exact=True).click()
            for level in ["Employee", "Managerial", "Corporate"]:
                expect(page.get_by_role("listbox", name="Performance level", exact=True).get_by_role("option", name=level, exact=True)).to_be_visible()
            page.get_by_role("listbox", name="Performance level", exact=True).get_by_role("option", name="All levels", exact=True).click()
            dialog.get_by_role("button", name="Clear filters", exact=True).click()
            assert "team=" not in page.url and "function=" not in page.url
            dialog.get_by_role("button", name="Done", exact=True).click()
            expect(roster.locator("li").first).to_be_visible()
            result["checks"].append("All three performance levels and clear-filter icon work")
            dialog = open_filters()
            dialog.get_by_role("button", name="Team", exact=True).click()
            page.get_by_role("listbox", name="Team", exact=True).get_by_role("option", name="Coding", exact=True).click()
            dialog.get_by_role("button", name="Done", exact=True).click()
            expect(roster.locator("li").first).to_be_visible()
            page.locator("aside").get_by_role("link", name="RCM", exact=True).click()
            team_roster_link = page.locator('.rf-page--team-dashboard a[href^="/employee/"]').first
            expect(team_roster_link).to_be_visible(timeout=60_000)
            page.wait_for_load_state("networkidle")
            assert urlparse(page.url).path.startswith("/team/")
            result["checks"].append("Team navigation opens its details page")
            request_count_before_return = len(result["requests"])
            begin = time.perf_counter()
            page.locator("aside").get_by_role("link", name="Executive Summary", exact=True).click()
            expect(roster.locator("li").first).to_be_visible()
            assert "team=" not in page.url and "function=" not in page.url
            result["warm_return_to_summary_ms"] = round((time.perf_counter() - begin) * 1000)
            result["checks"].append("Return home clears team filters and keeps summary data")
            page.wait_for_load_state("networkidle")
            # Team details may have their own bounded record reads; summary must not reread its roster.
            assert not any(request["path"] == "/api/performance/records" and "score_lt=90" in request["query"]
                for request in result["requests"][request_count_before_return:]), "Warm return must not reload the cached roster"
            result["checks"].append("Warm summary return reuses the cached roster")
            for width in [390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 844 if width == 390 else 1000})
                dialog = open_filters()
                expect(dialog.get_by_role("button", name="Done", exact=True)).to_be_visible()
                assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), f"Filter overflow at {width}px"
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Page overflow at {width}px"
                page.keyboard.press("Escape")
                expect(dialog).not_to_be_visible()
                result["checks"].append(f"Filters fit {width}px viewport and close with Escape")
            assert not page.get_by_role("alert").count(), "Unexpected visible error"
            result["checks"].append("No visible errors or uncaught browser exceptions")
            for path in ["/api/config/teams", "/api/team-management/management-kpi-config/teams"]:
                assert len([request for request in result["requests"] if request["path"] == path]) == 1, "Duplicate config reads"
            assert len([request for request in result["requests"] if request["path"] == "/api/executive/summary" and request["status"] == 404]) <= 1
            result["checks"].append("Configuration reads are deduplicated; unavailable endpoint is not repeatedly probed")
            chart = page.locator('[aria-labelledby="exec-hero-title"]').get_by_role("group", name=re.compile(r"trend, last six months:"))
            point = chart.locator('g[role="img"][tabindex="0"]')
            point.focus()
            tooltip = page.get_by_test_id("executive-trend-tooltip")
            expect(tooltip).to_be_visible()
            assert "%" in tooltip.inner_text()
            assert not re.search(r"\b(?:pp|pts)\b", tooltip.inner_text())
            point.press("ArrowLeft")
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            expect(tooltip).not_to_be_visible()
            result["checks"].append("Interactive trend uses % values and supports keyboard navigation")
            page.get_by_role("link", name="View RCM function", exact=True).click()
            page.wait_for_url(re.compile(r"/function-summary/rcm"))
            expect(page.get_by_role("heading", name="Function Summary", exact=True)).to_be_visible()
            assert not page.get_by_role("heading", name="Reports & export", exact=True).count()
            page.locator("aside").get_by_role("link", name="Executive Summary", exact=True).click()
            expect(roster.locator("li").first).to_be_visible()
            result["checks"].append("RCM function details open and have no reports/export section")
            samples = []
            for _ in range(3):
                page.locator("aside").get_by_role("link", name="RCM", exact=True).click()
                expect(team_roster_link).to_be_visible(timeout=60_000)
                page.wait_for_load_state("networkidle")
                begin = time.perf_counter()
                page.locator("aside").get_by_role("link", name="Executive Summary", exact=True).click()
                expect(roster.locator("li").first).to_be_visible()
                samples.append(round((time.perf_counter() - begin) * 1000))
            result["warm_return_samples_ms"] = samples
            result["warm_return_median_ms"] = sorted(samples)[1]
            full_reads = [request for request in result["requests"] if request["path"] == "/api/performance/records" and "detail=full" in request["query"]]
            assert full_reads, "Team details must load actual employee records"
            assert all("team=RCM" in request["query"] for request in full_reads), "Team drilldowns downloaded unrelated teams"
            first_batches = [request["query"] for request in full_reads if not request["cursor_page"]]
            assert len(first_batches) == len(set(first_batches)), "Warm team navigation repeated a cached period read"
            result["checks"].append("Repeated RCM drilldowns reuse team-scoped period reads without duplicates")
        result["resource_metrics"] = page.evaluate("""() => ({
            resources: performance.getEntriesByType('resource').length,
            transferredBytes: performance.getEntriesByType('resource').reduce((n,r)=>n+r.transferSize,0),
            domContentLoadedMs: performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd
        })""")
        if os.environ.get("PMS_E2E_BRANCH_USERNAME"):
            branch_context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            branch_page = branch_context.new_page()
            branch_page.set_default_timeout(30_000)
            branch_page.on("pageerror", lambda error: result["errors"].append(str(error)))
            branch_page.goto(base + "/login")
            branch_page.wait_for_load_state("networkidle")
            branch_page.get_by_label("Username", exact=True).fill(os.environ["PMS_E2E_BRANCH_USERNAME"])
            branch_page.get_by_label("Password", exact=True).fill(os.environ["PMS_E2E_BRANCH_PASSWORD"])
            with branch_page.expect_response(re.compile(r"/api/auth/login$")) as login_response:
                branch_page.get_by_role("button", name="Sign In", exact=True).click()
            token = login_response.value.json()["data"]["access_token"]
            branch_page.wait_for_url(re.compile(r"/executive(?:\?|$)"))
            expect(branch_page.locator('[aria-labelledby="exec-employees-below-title"] li').first).to_be_visible(timeout=60_000)
            branch_page.wait_for_load_state("networkidle")
            branch_page.get_by_role("button", name=re.compile(r"^Executive filters[.,]")).click()
            branch_dialog = branch_page.get_by_role("dialog", name="Executive filters", exact=True)
            locked = branch_dialog.locator('[data-locked="true"]').filter(has_text="Dubai")
            expect(locked).to_have_attribute("aria-disabled", "true")
            expect(branch_dialog.get_by_role("button", name="Branch", exact=True)).to_have_count(0)
            branch_dialog.get_by_role("button", name="Function", exact=True).click()
            branch_page.get_by_role("listbox", name="Function", exact=True).get_by_role("option", name="RCM", exact=True).click()
            branch_dialog.get_by_role("button", name="Clear filters", exact=True).click()
            expect(locked).to_have_attribute("aria-disabled", "true")
            result["checks"].append("Branch Director branch is locked and clearing filters preserves the restriction")
            for link in ["All Teams", "Reports", "Insights", "Planning", "Corrective Actions", "Function Summary"]:
                expect(branch_page.locator("aside").get_by_role("link", name=link, exact=True)).to_have_count(0)
            result["checks"].append("Branch Director navigation hides restricted workspaces")
            api_base = os.environ.get("PMS_E2E_API_URL", "http://127.0.0.1:8000")
            assert urlparse(api_base).hostname in {"127.0.0.1", "localhost"}
            denied = branch_context.request.get(api_base + "/api/performance/records?period=2026-08&branch=sharjah&detail=table&page_size=8", headers={"Authorization": "Bearer " + token})
            if denied.status == 200:
                data = denied.json().get("data", {})
                assert data.get("items") == [], "Out-of-scope branch returned records"
                assert data.get("total") in {None, 0}, "Out-of-scope branch leaked a record count"
            else:
                assert denied.status == 403, f"Unexpected out-of-scope response: {denied.status}"
            result["checks"].append("Backend returns no data for Branch Director reads from an unassigned branch")
            branch_dialog.get_by_role("button", name="Done", exact=True).click()
            branch_page.locator("aside").get_by_role("link", name="Settings", exact=True).click()
            expect(branch_page.get_by_role("heading", name="Administrator access required", exact=True)).to_be_visible()
            result["checks"].append("Branch Director cannot access Admin settings content")
            branch_page.get_by_role("button", name="Log out", exact=True).click()
            expect(branch_page.get_by_label("Username", exact=True)).to_be_visible()
            branch_context.close()
        if not args.inspect:
            page.get_by_role("button", name="Log out", exact=True).click()
            expect(page.get_by_label("Username", exact=True)).to_be_visible()
            assert page.evaluate("localStorage.getItem('pms_session_v1')") is None
            result["checks"].append("Sign-out removes the saved user session and returns to login")
        context.close()
        browser.close()
    directory = Path(__file__).parent / "artifacts"
    directory.mkdir(exist_ok=True)
    report_path = directory / (re.sub(r"[^a-zA-Z0-9_-]", "", args.report) + ".json")
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    assert not result["errors"], "Unexpected browser errors"


if __name__ == "__main__":
    run()
