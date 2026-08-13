"""Build the Marketing performance summary presentation from report data.

The report used to read a fixed workbook and contained hard-coded June numbers.
Keeping the builder data-only makes the Reports page's selected period the single
source of truth and keeps the generated deck aligned with the dashboard/API.
"""

from __future__ import annotations

import io
from collections import defaultdict
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt


SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5

BG = RGBColor(246, 249, 253)
WHITE = RGBColor(255, 255, 255)
NAVY = RGBColor(15, 23, 42)
MUTED = RGBColor(71, 85, 105)
FAINT = RGBColor(100, 116, 139)
BLUE = RGBColor(37, 99, 235)
PURPLE = RGBColor(124, 58, 237)
GREEN = RGBColor(5, 150, 105)
RED = RGBColor(225, 29, 72)
AMBER = RGBColor(217, 119, 6)
LINE = RGBColor(226, 232, 240)
PALE_BLUE = RGBColor(239, 246, 255)
PALE_RED = RGBColor(255, 241, 242)
PALE_GREEN = RGBColor(236, 253, 245)
PALE_AMBER = RGBColor(255, 251, 235)


def _ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 2:
        number /= 100
    return max(0.0, number)


def _weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number / 100 if number > 1 else max(number, 0.0)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _fmt_percent(value: Any, decimals: int = 1) -> str:
    number = _number(value)
    return "N/A" if number is None else f"{number:.{decimals}f}%"


def _fmt_value(value: Any, unit: str = "") -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    if unit == "%":
        return _fmt_percent(number)
    if abs(number) >= 1000:
        return f"{number:,.0f} {unit}".strip()
    if number.is_integer():
        return f"{number:,.0f} {unit}".strip()
    return f"{number:,.1f} {unit}".strip()


def _short(text: Any, limit: int = 115) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _color_for_gap(gap: float) -> RGBColor:
    return RED if gap >= 0.25 else AMBER if gap >= 0.1 else BLUE


def _shape(slide, geometry, left, top, width, height, fill=WHITE, line=LINE, radius=True):
    shape = slide.shapes.add_shape(geometry, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(1)
    return shape


def _text(slide, left, top, width, height, value, *, size=14, color=NAVY, bold=False,
          align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP, font="Aptos"):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.02)
    frame.margin_right = Inches(0.02)
    frame.margin_top = Inches(0.01)
    frame.margin_bottom = Inches(0.01)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.text = str(value)
    paragraph.alignment = align
    paragraph.font.name = font
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = color
    return box


def _header(slide, title: str, subtitle: str, accent=BLUE):
    _shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_WIDTH, 0.12, accent, accent)
    _text(slide, 0.65, 0.38, 11.7, 0.42, title, size=25, bold=True)
    _text(slide, 0.65, 0.86, 11.7, 0.28, subtitle, size=11, color=MUTED)
    _shape(slide, MSO_SHAPE.RECTANGLE, 0.65, 1.22, 12.03, 0.015, LINE, LINE)


def _footer(slide, period_label: str, slide_number: int):
    _text(slide, 0.65, 7.16, 9.5, 0.18, f"Marketing PMS • {period_label} • Confidential", size=8, color=FAINT)
    _text(slide, 11.95, 7.16, 0.7, 0.18, str(slide_number), size=8, color=FAINT, align=PP_ALIGN.RIGHT)


def _metric_card(slide, left, top, width, label, value, detail, accent, fill=WHITE):
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, 1.22, fill, LINE)
    _shape(slide, MSO_SHAPE.RECTANGLE, left, top, 0.07, 1.22, accent, accent)
    _text(slide, left + 0.22, top + 0.16, width - 0.42, 0.2, label.upper(), size=9, color=FAINT, bold=True)
    _text(slide, left + 0.22, top + 0.42, width - 0.42, 0.38, value, size=24, bold=True)
    _text(slide, left + 0.22, top + 0.88, width - 0.42, 0.2, detail, size=9, color=accent, bold=True)


def _prepare_payload(period_label: str, records: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize records/actions and calculate the four requested story layers."""
    clean_records = []
    for record in records:
        clean_records.append({
            "employee_id": str(record.get("employee_id") or ""),
            "employee_name": str(record.get("employee_name") or "Unknown employee"),
            "position": str(record.get("position") or "Marketing"),
            "region": str(record.get("region") or ""),
            "score": _number(record.get("score")) or 0.0,
            "suggested_action": record.get("suggested_action") or "",
            "kpis": list(record.get("kpis") or []),
        })
    clean_actions = [dict(action) for action in actions]

    position_scores: dict[str, list[float]] = defaultdict(list)
    for record in clean_records:
        position_scores[record["position"]].append(record["score"])
    positions = [
        {
            "name": position,
            "score": sum(scores) / len(scores),
            "headcount": len(scores),
        }
        for position, scores in position_scores.items()
        if scores
    ]
    positions.sort(key=lambda item: item["score"])
    largest_gap = positions[0] if positions else {"name": "Marketing", "score": 0.0, "headcount": 0}
    largest_gap["gap"] = max(0.0, 80.0 - largest_gap["score"])

    grouped: dict[str, dict[str, Any]] = {}
    for record in clean_records:
        for kpi in record["kpis"]:
            key = str(kpi.get("kpi_key") or kpi.get("label") or "KPI")
            entry = grouped.setdefault(key, {
                "key": key,
                "label": str(kpi.get("label") or key),
                "unit": str(kpi.get("unit") or ""),
                "direction": str(kpi.get("direction") or "higher_better"),
                "ratios": [],
                "actuals": [],
                "targets": [],
                "weights": [],
                "records": [],
            })
            ratio = _ratio(kpi.get("achievement_ratio"))
            actual = _number(kpi.get("actual_value"))
            target = _number(kpi.get("target_value"))
            if ratio is None and actual is not None and target not in (None, 0):
                ratio = actual / target if entry["direction"] == "higher_better" else (target / actual if actual else 1.0)
            if ratio is None:
                continue
            ratio = min(ratio, 1.0)
            entry["ratios"].append(ratio)
            if actual is not None:
                entry["actuals"].append(actual)
            if target is not None:
                entry["targets"].append(target)
            entry["weights"].append(_weight(kpi.get("weight_applied")))
            entry["records"].append({"record": record, "ratio": ratio, "weight": _weight(kpi.get("weight_applied"))})

    kpis = []
    for entry in grouped.values():
        if not entry["ratios"]:
            continue
        avg_ratio = sum(entry["ratios"]) / len(entry["ratios"])
        avg_weight = sum(entry["weights"]) / len(entry["weights"]) if entry["weights"] else 0.0
        kpis.append({
            "key": entry["key"],
            "label": entry["label"],
            "unit": entry["unit"],
            "direction": entry["direction"],
            "average_ratio": avg_ratio,
            "average_actual": sum(entry["actuals"]) / len(entry["actuals"]) if entry["actuals"] else None,
            "average_target": sum(entry["targets"]) / len(entry["targets"]) if entry["targets"] else None,
            "weight": avg_weight,
            "weighted_gap": max(0.0, 1.0 - avg_ratio) * avg_weight,
            "affected": sorted(
                [
                    {
                        "record": item["record"],
                        "ratio": item["ratio"],
                        "gap": max(0.0, 1.0 - item["ratio"]),
                    }
                    for item in entry["records"]
                    if item["ratio"] < 1.0
                ],
                key=lambda item: item["gap"],
                reverse=True,
            ),
        })
    kpis.sort(key=lambda item: item["weighted_gap"], reverse=True)
    driver = kpis[0] if kpis else {
        "label": "No measured KPI gap", "average_ratio": 1.0, "weighted_gap": 0.0,
        "affected": [], "unit": "", "direction": "higher_better", "weight": 0.0,
        "average_actual": None, "average_target": None,
    }

    action_by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in clean_actions:
        employee_id = str(action.get("employee_id") or "")
        if employee_id:
            action_by_employee[employee_id].append(action)
    impacted_people = []
    for item in driver.get("affected", [])[:10]:
        record = item["record"]
        employee_actions = action_by_employee.get(record["employee_id"], [])
        impacted_people.append({
            "employee_id": record["employee_id"],
            "name": record["employee_name"],
            "position": record["position"],
            "actual_ratio": item["ratio"],
            "gap": item["gap"],
            "actions": employee_actions,
            "recommendation": record["suggested_action"] or (
                f"{'Reduce' if driver.get('direction') == 'lower_better' else 'Improve'} {driver['label']}; "
                "assign coaching and review the result weekly."
            ),
        })

    return {
        "period_label": period_label,
        "records": clean_records,
        "actions": clean_actions,
        "overall_score": sum(record["score"] for record in clean_records) / len(clean_records) if clean_records else 0.0,
        "employee_count": len({record["employee_id"] for record in clean_records if record["employee_id"]}),
        "largest_gap": largest_gap,
        "positions": positions,
        "kpis": kpis,
        "driver": driver,
        "impacted_people": impacted_people,
    }


def build_marketing_pptx(period_label: str = "June 2026", report_data: dict[str, Any] | None = None) -> bytes:
    """Return an editable, period-specific Marketing executive summary deck."""
    report_data = report_data or {}
    payload = _prepare_payload(period_label, list(report_data.get("records") or []), list(report_data.get("actions") or []))
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH)
    prs.slide_height = Inches(SLIDE_HEIGHT)

    # 1. Overall performance and the largest team/position gap.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG
    _header(slide, "Marketing performance summary", f"{period_label} • filtered report", BLUE)
    _text(slide, 0.65, 1.55, 8.2, 0.55, f"Marketing delivered {payload['overall_score']:.1f}% overall performance.", size=24, bold=True)
    _text(slide, 0.65, 2.18, 8.0, 0.38, "The first management question is where the largest performance gap is concentrated.", size=13, color=MUTED)
    _metric_card(slide, 0.65, 3.0, 3.7, "Overall score", _fmt_percent(payload["overall_score"]), f"{payload['employee_count']} employees in scope", BLUE, PALE_BLUE)
    gap = payload["largest_gap"]
    _metric_card(slide, 4.6, 3.0, 3.7, "Largest team / position gap", gap["name"], f"Score {_fmt_percent(gap['score'])} • {gap['gap']:.1f} pts below 80%", RED, PALE_RED)
    _metric_card(slide, 8.55, 3.0, 3.95, "People in the gap area", str(gap["headcount"]), "Employees represented by the largest gap", PURPLE, RGBColor(245, 243, 255))
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.65, 4.7, 11.85, 1.55, WHITE, LINE)
    _text(slide, 0.95, 4.98, 3.0, 0.22, "WHAT THIS MEANS", size=10, color=BLUE, bold=True)
    _text(slide, 0.95, 5.28, 10.9, 0.55,
          f"{gap['name']} is the largest contributor to the Marketing gap, averaging {gap['score']:.1f}% "
          f"against the 80% review benchmark. The next step is to isolate the KPI with the highest weighted impact.",
          size=16, bold=True)
    _footer(slide, period_label, 1)

    # 2. Biggest KPI causing the gap.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = BG
    driver = payload["driver"]
    _header(slide, "The largest gap is driven by one KPI", f"Weighted KPI impact • {period_label}", RED)
    _text(slide, 0.65, 1.55, 8.0, 0.46, str(driver.get("label") or "No measured KPI gap"), size=25, bold=True)
    _text(slide, 0.65, 2.08, 7.5, 0.35, "The ranking uses average achievement shortfall multiplied by the configured KPI weight.", size=12, color=MUTED)
    ratio = float(driver.get("average_ratio") or 0)
    _metric_card(slide, 0.65, 2.8, 3.1, "Average achievement", _fmt_percent(ratio * 100), f"Weighted gap {(driver.get('weighted_gap') or 0) * 100:.1f} pts", _color_for_gap(1 - ratio), PALE_RED if ratio < 0.75 else PALE_AMBER)
    _metric_card(slide, 3.95, 2.8, 3.1, "Average actual", _fmt_value(driver.get("average_actual"), driver.get("unit", "")), f"Target {_fmt_value(driver.get('average_target'), driver.get('unit', ''))}", BLUE, PALE_BLUE)
    direction_label = "Lower" if driver.get("direction") == "lower_better" else "Higher"
    _metric_card(slide, 7.25, 2.8, 2.55, "Direction", direction_label, f"{direction_label} is better • configured rule", PURPLE, RGBColor(245, 243, 255))
    _metric_card(slide, 9.98, 2.8, 2.52, "People affected", str(len(driver.get("affected") or [])), "Below target in this period", RED, PALE_RED)
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.65, 4.45, 11.85, 1.7, WHITE, LINE)
    _text(slide, 0.95, 4.72, 2.8, 0.2, "TOP KPI GAPS", size=10, color=RED, bold=True)
    ranked = payload["kpis"][:5]
    for index, item in enumerate(ranked):
        y = 5.08 + index * 0.22
        gap_pct = item["weighted_gap"] * 100
        _text(slide, 0.95, y, 4.5, 0.16, str(item["label"]), size=9, color=NAVY, bold=index == 0)
        _shape(slide, MSO_SHAPE.RECTANGLE, 5.0, y + 0.04, min(4.7, max(0.05, gap_pct / 10)), 0.08, RED if index == 0 else AMBER, RED if index == 0 else AMBER)
        _text(slide, 10.0, y, 1.8, 0.16, f"{gap_pct:.1f} pts", size=9, color=RED if index == 0 else AMBER, bold=True, align=PP_ALIGN.RIGHT)
    _footer(slide, period_label, 2)

    # 3. People contributing to the KPI gap.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = BG
    _header(slide, "People contributing to the KPI gap", f"Employees most affected by {driver.get('label', 'the selected KPI')}", PURPLE)
    columns = [(0.65, 2.7, "EMPLOYEE"), (3.4, 2.35, "POSITION"), (5.9, 1.65, "ACHIEVEMENT"), (7.75, 1.55, "GAP"), (9.5, 3.0, "CURRENT SIGNAL")]
    for left, width, label in columns:
        _text(slide, left, 1.52, width, 0.22, label, size=9, color=FAINT, bold=True)
    _shape(slide, MSO_SHAPE.RECTANGLE, 0.65, 1.82, 11.85, 0.02, LINE, LINE)
    people = payload["impacted_people"][:8]
    if not people:
        _text(slide, 0.9, 2.3, 10.5, 0.4, "No employee is below target for the selected KPI in this period.", size=17, color=GREEN, bold=True)
    for index, person in enumerate(people):
        y = 1.98 + index * 0.56
        if index % 2 == 0:
            _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.65, y - 0.05, 11.85, 0.48, WHITE, WHITE)
        _text(slide, 0.82, y + 0.04, 2.45, 0.24, _short(person["name"], 32), size=10, bold=True)
        _text(slide, 3.4, y + 0.04, 2.25, 0.24, _short(person["position"], 28), size=10, color=MUTED)
        _text(slide, 5.9, y + 0.04, 1.55, 0.24, _fmt_percent(person["actual_ratio"] * 100), size=10, color=RED, bold=True)
        _text(slide, 7.75, y + 0.04, 1.35, 0.24, f"-{person['gap'] * 100:.1f} pts", size=10, color=RED, bold=True)
        action_state = "Action recorded" if person["actions"] else "Recommendation needed"
        _text(slide, 9.5, y + 0.04, 2.85, 0.24, action_state, size=10, color=GREEN if person["actions"] else AMBER, bold=True)
    _footer(slide, period_label, 3)

    # 4. Actions taken or recommended.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = BG
    _header(slide, "Actions taken and next actions", f"Close the gap with accountable follow-up • {period_label}", GREEN)
    _text(slide, 0.65, 1.52, 11.5, 0.35, "Existing active actions are shown first; employees without an action receive a system recommendation.", size=12, color=MUTED)
    action_rows = []
    for person in payload["impacted_people"][:6]:
        action = person["actions"][0] if person["actions"] else None
        action_rows.append({
            "name": person["name"],
            "kind": f"Taken • {action.get('action_type', 'Action')}" if action else "Recommended",
            "text": action.get("action_text") if action else person["recommendation"],
            "status": action.get("status", "Open") if action else "Proposed",
            "root": action.get("root_cause_note", "") if action else f"{driver.get('label', 'KPI')} below target",
        })
    for extra in payload["actions"]:
        if not any(row["name"] == extra.get("employee_name") for row in action_rows):
            action_rows.append({
                "name": extra.get("employee_name") or "Team action",
                "kind": f"Taken • {extra.get('action_type', 'Action')}",
                "text": extra.get("action_text") or "Action recorded",
                "status": extra.get("status", "Open"),
                "root": extra.get("root_cause_note", ""),
            })
    if not action_rows:
        action_rows = [{
            "name": "Marketing leadership", "kind": "Recommended", "text": f"Review {driver.get('label', 'the KPI')} weekly and assign coaching to the affected positions.", "status": "Proposed", "root": "No active corrective action was found for this period.",
        }]
    for index, row in enumerate(action_rows[:6]):
        y = 2.08 + index * 0.75
        fill = PALE_GREEN if row["kind"].startswith("Taken") else PALE_AMBER
        accent = GREEN if row["kind"].startswith("Taken") else AMBER
        _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.65, y, 11.85, 0.62, fill, LINE)
        _text(slide, 0.9, y + 0.1, 2.6, 0.2, _short(row["name"], 30), size=10, bold=True)
        _text(slide, 3.55, y + 0.1, 2.15, 0.2, row["kind"], size=9, color=accent, bold=True)
        _text(slide, 5.85, y + 0.08, 4.85, 0.3, _short(row["text"], 85), size=9, color=NAVY)
        _text(slide, 10.85, y + 0.1, 1.35, 0.2, row["status"], size=9, color=accent, bold=True, align=PP_ALIGN.RIGHT)
    _footer(slide, period_label, 4)

    # 5. Close with a decision-ready summary.
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = BG
    _header(slide, "Management focus for the next review", f"A concise action plan from the {period_label} evidence", BLUE)
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.65, 1.6, 7.4, 4.75, WHITE, LINE)
    _text(slide, 0.95, 1.92, 6.8, 0.28, "DECISION SUMMARY", size=10, color=BLUE, bold=True)
    summary = [
        f"1. Overall performance: {payload['overall_score']:.1f}% across {payload['employee_count']} employees.",
        f"2. Largest gap: {gap['name']} at {gap['score']:.1f}% versus the 80% review benchmark.",
        f"3. KPI driver: {driver.get('label', 'No measured KPI gap')} with {float(driver.get('weighted_gap') or 0) * 100:.1f} weighted gap points.",
        f"4. People to review: {len(payload['impacted_people'])} employees below the selected KPI target.",
        f"5. Follow-up: {len(payload['actions'])} active action(s) recorded; fill the remaining recommendations with accountable owners.",
    ]
    for index, line in enumerate(summary):
        _text(slide, 0.95, 2.42 + index * 0.62, 6.65, 0.46, line, size=14, color=NAVY, bold=index == 2)
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 8.35, 1.6, 4.15, 4.75, PALE_BLUE, BLUE)
    _text(slide, 8.7, 1.95, 3.45, 0.25, "RECOMMENDED NEXT STEP", size=10, color=BLUE, bold=True)
    _text(slide, 8.7, 2.45, 3.35, 1.3, f"Assign an owner to {driver.get('label', 'the leading KPI gap')}, review the affected employees weekly, and confirm movement in the next filtered-month report.", size=17, bold=True)
    _text(slide, 8.7, 4.45, 3.35, 0.6, "The report is generated from the selected month’s performance records and active corrective actions.", size=11, color=MUTED)
    _footer(slide, period_label, 5)

    output = io.BytesIO()
    prs.save(output)
    return output.getvalue()
