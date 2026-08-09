from __future__ import annotations

import hashlib
import io
import textwrap
from datetime import datetime, timezone
from typing import Any


PAGE_W, PAGE_H = 960, 540


def _clean(value: Any) -> str:
    text = "N/A" if value is None else str(value)
    return " ".join(text.replace("\r", " ").replace("\n", " ").encode("latin-1", "replace").decode("latin-1").split())


def _esc(value: Any) -> str:
    return _clean(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text(x: float, y: float, value: Any, size: int = 10, color=(25, 38, 62), bold: bool = False) -> str:
    r, g, b = (component / 255 for component in color)
    font = "F2" if bold else "F1"
    return f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.1f} {y:.1f} Tm ({_esc(value)}) Tj ET"


def _rect(x: float, y: float, w: float, h: float, fill=(248, 250, 252), stroke=(220, 228, 239), radius: int = 0) -> str:
    del radius
    fr, fg, fb = (component / 255 for component in fill)
    sr, sg, sb = (component / 255 for component in stroke)
    return f"{fr:.3f} {fg:.3f} {fb:.3f} rg {sr:.3f} {sg:.3f} {sb:.3f} RG 1 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re B"


LAYOUT_BOUNDS = {
    "cover": {"cover": (54, 70, 852, 370)}, "closing_page": {"full": (54, 70, 852, 370)},
    "department_divider": {"full": (54, 70, 852, 370)}, "full_width": {"full": (54, 70, 852, 390)},
    "two_blocks": {"left": (54, 70, 414, 390), "right": (492, 70, 414, 390)},
    "four_kpis": {"summary": (54, 90, 852, 350)},
    "kpi_chart": {"summary": (54, 330, 852, 110), "chart": (54, 70, 852, 240)},
    "kpi_chart_narrative": {"summary": (54, 350, 852, 90), "chart": (54, 175, 852, 155), "narrative": (54, 70, 852, 85)},
    "two_charts": {"chart_left": (54, 70, 414, 370), "chart_right": (492, 70, 414, 370)},
    "chart_table": {"chart": (54, 70, 414, 370), "table": (492, 70, 414, 370)},
    "chart_narrative": {"chart": (54, 70, 520, 370), "narrative": (594, 70, 312, 370)},
    "table_narrative": {"table": (54, 70, 560, 370), "narrative": (634, 70, 272, 370)},
    "two_tables": {"table_left": (54, 70, 414, 370), "table_right": (492, 70, 414, 370)},
    "comparison": {"chart_left": (54, 70, 414, 370), "chart_right": (492, 70, 414, 370)},
    "risk_actions": {"insights": (54, 70, 414, 370), "actions": (492, 70, 414, 370)},
    "insights_decisions": {"insights": (54, 70, 414, 370), "decisions": (492, 70, 414, 370)},
    "actions_planning": {"actions": (54, 70, 414, 370), "planning": (492, 70, 414, 370)},
    "closing_decisions": {"narrative": (54, 70, 414, 370), "decisions": (492, 70, 414, 370)},
    "root_cause_actions": {"insights": (54, 70, 414, 370), "actions": (492, 70, 414, 370)},
    "process_staff_actions": {"table_left": (54, 70, 414, 370), "table_right": (492, 70, 414, 370)},
    "feedback_status": {"summary": (54, 340, 852, 100), "table": (54, 70, 852, 250)},
    "decisions_next_steps": {"narrative": (54, 70, 414, 370), "decisions": (492, 70, 414, 370)},
    "team_review": {"overview": (54, 270, 414, 170), "trend": (492, 270, 414, 170), "analysis": (54, 70, 852, 180)},
}


MANAGEMENT_TABLE_COLUMNS = {
    "lowest_kpis_weighted_impact": [("rank", "#"), ("name", "KPI"), ("team", "Scope"), ("actual", "Actual"), ("target", "Target"), ("lost_points", "Lost %")],
    "lowest_employees_current_period": [("rank", "#"), ("employee", "Employee"), ("team", "Team"), ("current_score", "Score"), ("weakest_scored_kpi", "Weakest KPI"), ("weighted_lost_points", "Lost %")],
    "three_month_consecutive_low_performers": [("employee", "Employee"), ("team", "Team"), ("three_month_average", "3M Avg"), ("trend", "Trend"), ("repeated_weakest_kpi", "Repeated KPI"), ("current_action_status", "Action")],
    "applied_configuration_audit": [("severity", "Severity"), ("issue", "Issue"), ("scope", "Scope"), ("kpi", "KPI"), ("effect_on_analysis", "Analysis Effect"), ("recommended_correction", "Correction")],
    "root_cause_evidence_matrix": [("cause_title", "Cause"), ("classification", "Class"), ("confidence", "Confidence"), ("scope", "Scope"), ("linked_kpi", "KPI"), ("impact_type", "Evidence Measure")],
}


def _render_management_table(block_type: str, data: dict, bounds: tuple[float, float, float, float], row_limit: int) -> list[str]:
    x, y, w, h = bounds
    rows = list(data.get("rows") or [])[: min(row_limit, 10)]
    columns = MANAGEMENT_TABLE_COLUMNS[block_type]
    commands: list[str] = []
    col_w = (w - 24) / len(columns)
    for index, (_key, label) in enumerate(columns):
        commands.append(_text(x + 12 + index * col_w, y + h - 50, label[:18], 7, color=(91, 105, 128), bold=True))
    row_h = min(31, max(22, (h - 82) / max(1, len(rows))))
    wrap_width = max(12, int(col_w / 4.4))
    for row_index, row in enumerate(rows):
        row_y = y + h - 72 - row_index * row_h
        if row_y < y + 28:
            break
        if row_index % 2 == 0:
            commands.append(_rect(x + 8, row_y - 7, w - 16, row_h, fill=(248, 250, 252), stroke=(248, 250, 252)))
        for index, (key, _label) in enumerate(columns):
            value = _clean(row.get(key))
            if block_type == "lowest_kpis_weighted_impact" and key in {"actual", "target"} and row.get(key) is not None:
                value = f"{value} {_clean(row.get('unit'))}"
            if key in {"lost_points", "weighted_lost_points"} and row.get(key) is not None:
                value = f"{value}%"
            lines = textwrap.wrap(value, width=wrap_width)[:2] or ["N/A"]
            for line_index, line in enumerate(lines):
                commands.append(_text(x + 12 + index * col_w, row_y - line_index * 9, line, 6 if len(lines) > 1 else 7, color=(62, 77, 100), bold=key in {"rank", "lost_points", "weighted_lost_points"}))
    if len(data.get("rows") or []) > len(rows):
        commands.append(_text(x + 12, y + 12, f"Showing {len(rows)} of {len(data['rows'])}", 7, color=(91, 105, 128), bold=True))
    exclusions = len(data.get("configuration_issues_excluded") or [])
    insufficient = len(data.get("insufficient_history") or [])
    note = f"{exclusions} configuration issue(s) excluded from ranking" if exclusions else f"{insufficient} employee(s) excluded for insufficient consecutive history" if insufficient else None
    if note:
        commands.append(_text(x + w - 280, y + 12, note, 7, color=(180, 104, 8), bold=True))
    return commands


def _render_movement_bridge(data: dict, bounds: tuple[float, float, float, float]) -> list[str]:
    x, y, w, h = bounds
    previous, current, movement = data.get("previous_overall_score"), data.get("current_overall_score"), data.get("total_score_point_change")
    commands = [_text(x + 18, y + h - 58, data.get("comparison_period") or "Previous", 8, color=(91, 105, 128), bold=True),
                _text(x + 18, y + h - 88, f"{previous:.1f}%" if previous is not None else "N/A", 19, bold=True),
                _text(x + w - 135, y + h - 58, data.get("current_period") or "Current", 8, color=(91, 105, 128), bold=True),
                _text(x + w - 135, y + h - 88, f"{current:.1f}%" if current is not None else "N/A", 19, bold=True),
                _text(x + w / 2 - 44, y + h - 72, f"{movement:+.2f}%" if movement is not None else "N/A", 14, color=(8, 145, 102) if (movement or 0) >= 0 else (225, 51, 85), bold=True)]
    effects = [{"label": item.get("label"), "value": item.get("score_point_change")} for item in data.get("kpi_contribution_movements", [])]
    effects.extend([
        {"label": "Joiners", "value": data.get("joiner_effect")}, {"label": "Leavers", "value": data.get("leaver_effect")},
        {"label": "Scope mix", "value": data.get("population_scope_mix_effect")}, {"label": "Configuration", "value": data.get("configuration_version_effect")},
        {"label": "Incomparable data", "value": data.get("missing_incomparable_data_effect")}, {"label": "Residual", "value": data.get("residual")},
    ])
    effects = [item for item in effects if item["value"] is not None][:10]
    maximum = max([abs(float(item["value"])) for item in effects] or [1]) or 1
    for index, item in enumerate(effects):
        row_y = y + h - 132 - index * 22
        value = float(item["value"])
        commands.append(_text(x + 18, row_y, item["label"][:30], 7, color=(62, 77, 100)))
        bar_x = x + w * .35
        bar_w = max(2, w * .25 * abs(value) / maximum)
        fill = (24, 188, 145) if value >= 0 else (255, 72, 105)
        commands.append(_rect(bar_x if value >= 0 else bar_x - bar_w, row_y - 3, bar_w, 8, fill=fill, stroke=fill))
        commands.append(_text(x + w * .66, row_y, f"{value:+.2f}%", 7, color=fill, bold=True))
    narrative = textwrap.wrap(_clean(data.get("narrative")), width=max(60, int(w / 6.5)))
    for index, line in enumerate(narrative[:3]):
        commands.append(_text(x + 18, y + 34 - index * 11, line, 7, color=(91, 105, 128)))
    commands.append(_text(x + w - 155, y + 12, str(data.get("reconciliation_state", "unavailable")).upper(), 7, color=(8, 145, 102) if data.get("reconciliation_state") == "reconciled" else (180, 104, 8), bold=True))
    return commands


def _render_block(block: dict, result: dict, bounds: tuple[float, float, float, float], commentary: str = "") -> list[str]:
    x, y, w, h = bounds
    commands = [_rect(x, y, w, h)]
    title = block.get("config", {}).get("title") or block.get("type", "").replace("_", " ").title().replace("Kpi", "KPI")
    commands.append(_text(x + 14, y + h - 22, title, 11, bold=True))
    state = result.get("state", "no_data")
    data = result.get("data") or {}
    if state != "ready":
        message = (result.get("warnings") or ["No data is available for this scope and period."])[0]
        commands.append(_text(x + 14, y + h - 48, message, 9, color=(116, 129, 151)))
        return commands
    if commentary and block.get("type") == "management_commentary":
        data = {"narrative": commentary}
    block_type = block.get("type")
    if block_type == "overall_score_movement_bridge":
        commands.extend(_render_movement_bridge(data, bounds))
        return commands
    if block_type in MANAGEMENT_TABLE_COLUMNS:
        commands.extend(_render_management_table(block_type, data, bounds, int(block.get("config", {}).get("row_limit", 10))))
        return commands
    metrics = data.get("metrics")
    if metrics:
        card_w = (w - 20) / min(4, len(metrics))
        for index, metric in enumerate(metrics[:4]):
            cx = x + 10 + index * card_w
            commands.append(_text(cx + 6, y + h - 55, metric.get("label", "Metric"), 7, color=(91, 105, 128), bold=True))
            commands.append(_text(cx + 6, y + h - 82, metric.get("display", metric.get("value", "N/A")), 15, bold=True))
            if metric.get("change_display"):
                color = (8, 145, 102) if metric.get("movement") == "positive" else (225, 51, 85)
                commands.append(_text(cx + 6, y + h - 99, metric["change_display"], 7, color=color))
        if block.get("type") == "insights_summary" and data.get("narrative"):
            lines = textwrap.wrap(_clean(data["narrative"]), width=max(32, int(w / 7)))
            for index, line in enumerate(lines[: max(1, int((h - 125) / 12))]):
                commands.append(_text(x + 14, y + h - 122 - index * 12, line, 8, color=(62, 77, 100)))
        return commands
    series = data.get("series") or data.get("items")
    if series and isinstance(series, list) and series and isinstance(series[0], dict) and ("value" in series[0] or "impact" in series[0]):
        values = [abs(float(item.get("value", item.get("impact", 0)) or 0)) for item in series[:8]]
        maximum = max(values) or 1
        row_h = min(31, (h - 55) / max(1, len(values)))
        for index, item in enumerate(series[:8]):
            row_y = y + h - 50 - (index + 1) * row_h
            label = item.get("label") or item.get("name") or item.get("kpi") or "Item"
            value = float(item.get("value", item.get("impact", 0)) or 0)
            commands.append(_text(x + 14, row_y + 7, label[:30], 7))
            bar_x, bar_w = x + w * .42, (w * .5) * abs(value) / maximum
            fill = (24, 188, 145) if value >= 0 else (255, 72, 105)
            commands.append(_rect(bar_x, row_y + 3, max(2, bar_w), 10, fill=fill, stroke=fill))
            label_x = x + w - 52
            label_color = (255, 255, 255) if bar_x + bar_w >= label_x - 3 else fill
            commands.append(_text(label_x, row_y + 5, item.get("display", f"{value:+.1f}%"), 7, color=label_color, bold=True))
        return commands
    rows = data.get("rows") or data.get("root_causes") or data.get("actions")
    if rows and isinstance(rows, list):
        if block.get("type") == "agenda":
            per_column = 9
            column_w = (w - 32) / 2
            for index, row in enumerate(rows[:18]):
                column = index // per_column
                row_index = index % per_column
                row_y = y + h - 58 - row_index * 34
                row_x = x + 14 + column * (column_w + 8)
                commands.append(_text(row_x, row_y, str(row.get("page", index + 1)).zfill(2), 8, color=(37, 99, 235), bold=True))
                commands.append(_text(row_x + 28, row_y, _clean(row.get("title"))[:42], 8, color=(48, 63, 86), bold=True))
            return commands
        hidden = {"employee_id", "is_below", "validation", "projection_assumptions"}
        keys = [key for key in rows[0].keys() if key not in hidden][:5]
        columns = max(1, len(keys)); col_w = (w - 20) / columns
        for column, key in enumerate(keys):
            commands.append(_text(x + 10 + column * col_w, y + h - 50, key.replace("_", " ").title()[:18], 7, bold=True))
        for row_index, row in enumerate(rows[:8]):
            row_y = y + h - 70 - row_index * 24
            if row_y < y + 14: break
            for column, key in enumerate(keys):
                commands.append(_text(x + 10 + column * col_w, row_y, _clean(row.get(key))[:22], 7, color=(70, 85, 107)))
        row_summary = data.get("row_summary") or {}
        if row_summary.get("total", 0) > row_summary.get("shown", 0):
            commands.append(_text(x + 10, y + 10, f"Showing {row_summary['shown']} of {row_summary['total']}", 7, color=(91, 105, 128), bold=True))
        return commands
    narrative = data.get("narrative") or data.get("text") or data.get("summary")
    if narrative:
        lines = textwrap.wrap(_clean(narrative), width=max(32, int(w / 7)))
        for index, line in enumerate(lines[: max(2, int((h - 50) / 14))]):
            commands.append(_text(x + 14, y + h - 50 - index * 14, line, 9, color=(62, 77, 100)))
    return commands


def build_presentation_pdf(*, report_name: str, definition: dict, slide_data: dict, commentary: dict, metadata: dict) -> bytes:
    pages: list[bytes] = []
    slides = sorted(definition.get("slides", []), key=lambda item: item.get("order", 0))
    for page_index, slide in enumerate(slides, start=1):
        if slide.get("layout") == "cover":
            commands = [_rect(0, 0, PAGE_W, PAGE_H, fill=(20, 46, 91), stroke=(20, 46, 91))]
            title_lines = textwrap.wrap(_clean(report_name), width=36)[:3]
            for index, line in enumerate(title_lines):
                commands.append(_text(86, 360 - index * 44, line, 30, color=(255, 255, 255), bold=True))
            commands.append("0.145 0.388 0.922 rg 86 285 120 5 re f")
            commands.append(_text(86, 245, metadata.get("primary_period", "Reporting period"), 16, color=(191, 219, 254), bold=True))
            commands.append(_text(86, 215, f"Compared with {metadata.get('comparison_period', 'Unavailable')}", 11, color=(203, 213, 225)))
            commands.append(_text(86, 185, metadata.get("scope", "Authorized scope"), 11, color=(203, 213, 225)))
            commands.append(_text(86, 58, "SGH Hub Intelligence | Monthly Performance Review", 9, color=(147, 197, 253), bold=True))
            commands.append(_text(820, 58, f"Confidential | {page_index}/{len(slides)}", 8, color=(203, 213, 225)))
            pages.append("\n".join(commands).encode("latin-1", "replace"))
            continue
        commands = ["1 1 1 rg 0 0 960 540 re f"]
        commands.append(_text(54, 495, slide.get("title", "Untitled Page"), 20, bold=True))
        commands.append("0.118 0.376 0.953 rg 54 480 70 3 re f")
        layout_bounds = LAYOUT_BOUNDS.get(slide.get("layout"), LAYOUT_BOUNDS["full_width"])
        page_results = slide_data.get(slide.get("id"), {}).get("blocks", {})
        for block in slide.get("blocks", []):
            bounds = layout_bounds.get(block.get("slot"), next(iter(layout_bounds.values())))
            result = page_results.get(block.get("id"), {"state": "no_data", "warnings": ["Block data was not resolved."]})
            commands.extend(_render_block(block, result, bounds, commentary.get("entries", {}).get(block.get("id"), "")))
        footer = f"{metadata.get('scope', 'Authorized scope')} | {metadata.get('primary_period', '')} vs {metadata.get('comparison_period', 'N/A')} | Confidential | {page_index}/{len(slides)}"
        commands.append(_text(54, 25, footer, 7, color=(120, 132, 151)))
        commands.append(_text(820, 25, "SGH Hub Intelligence", 7, color=(37, 99, 235), bold=True))
        pages.append("\n".join(commands).encode("latin-1", "replace"))

    objects: dict[int, bytes] = {
        1: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        2: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    }
    content_ids, page_ids = [], []
    next_id = 3
    for stream in pages:
        content_id, page_id = next_id, next_id + 1; next_id += 2
        content_ids.append(content_id); page_ids.append(page_id)
        objects[content_id] = f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
    pages_id, catalog_id = next_id, next_id + 1
    for content_id, page_id in zip(content_ids, page_ids):
        objects[page_id] = f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Resources << /Font << /F1 1 0 R /F2 2 0 R >> >> /Contents {content_id} 0 R >>".encode()
    objects[pages_id] = f"<< /Type /Pages /Kids [{' '.join(f'{value} 0 R' for value in page_ids)}] /Count {len(page_ids)} >>".encode()
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    output = io.BytesIO(); output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, catalog_id + 1):
        offsets.append(output.tell()); output.write(f"{object_id} 0 obj\n".encode() + objects[object_id] + b"\nendobj\n")
    xref = output.tell(); output.write(f"xref\n0 {catalog_id + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer\n<< /Size {catalog_id + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output.getvalue()


def pdf_integrity_identifier(file_data: bytes, snapshot_payload: bytes) -> str:
    return hashlib.sha256(snapshot_payload + b"\0" + file_data).hexdigest()
