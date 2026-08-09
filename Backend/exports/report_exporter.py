from __future__ import annotations

import io
import textwrap
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable, List
from xml.sax.saxutils import escape as xml_escape

import pandas as pd

from models.schemas import PerformanceRecord


class ReportExporter:
    @staticmethod
    def flatten_record(r: PerformanceRecord) -> dict:
        row = {
            "Employee ID": r.employee_id,
            "Employee Name": r.employee_name,
            "Team": r.team,
            "Position": r.position or "",
            "Region": r.region or "",
            "Performance Level": r.performance_level,
            "Year": r.year,
            "Month": r.month,
            "Performance Score": r.evaluation.score,
            "Grade": r.evaluation.grade,
            "Status": r.status or "",
            "Root Cause": r.evaluation.root_cause.kpi if r.evaluation.root_cause else "None",
            "Root Cause Gap": r.evaluation.root_cause.impact_pct if r.evaluation.root_cause else 0.0,
            "AI Suggested Action": r.evaluation.suggested_action or "None",
            "Manager Corrective Action": r.evaluation.corrective_action or "None",
            "Manager Notes": r.evaluation.manager_notes or "None",
            "Booking Rate (%)": round(r.actual.booking_rate * 100, 2),
            "Attendance Rate (%)": round(r.actual.attend_rate * 100, 2),
            "Abandon Rate (%)": round(r.actual.abandon_rate * 100, 2),
            "Inbound Calls": r.calls.inbound,
            "Outbound Calls": r.calls.outbound,
            "AHT": r.calls.aht_raw,
        }
        for value in r.kpi_values or []:
            label = str(value.get("label") or value.get("kpi_key") or "KPI")
            row[f"{label} Actual"] = value.get("actual_value")
            row[f"{label} Target"] = value.get("target_value")
            ratio = value.get("achievement_ratio")
            try:
                normalized_ratio = min(max(float(ratio), 0.0), 1.0) if ratio is not None else None
            except (TypeError, ValueError):
                normalized_ratio = None
            row[f"{label} Achievement (%)"] = round(normalized_ratio * 100, 2) if normalized_ratio is not None else None
            contribution = value.get("contribution")
            try:
                normalized_contribution = max(float(contribution), 0.0) if contribution is not None else None
                weight = value.get("weight_applied", value.get("weight"))
                if normalized_contribution is not None and weight is not None:
                    normalized_weight = float(weight)
                    if normalized_weight > 1:
                        normalized_weight /= 100
                    normalized_contribution = min(normalized_contribution, max(normalized_weight, 0.0))
                elif normalized_contribution is not None:
                    normalized_contribution = min(normalized_contribution, 1.0)
            except (TypeError, ValueError):
                normalized_contribution = None
            row[f"{label} Contribution (%)"] = round(normalized_contribution * 100, 2) if normalized_contribution is not None else None
        return row

    @staticmethod
    def export_to_excel(records: List[PerformanceRecord]) -> bytes:
        flat_records = [ReportExporter.flatten_record(record) for record in records]
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(flat_records).to_excel(writer, sheet_name="Performance Summary", index=False)
        return output.getvalue()

    @staticmethod
    def export_workbook(*, metadata: dict[str, Any], sheets: dict[str, list[dict[str, Any]]]) -> bytes:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame([{"Field": key, "Value": value} for key, value in metadata.items()]).to_excel(
                writer,
                sheet_name="Report Metadata",
                index=False,
            )
            for sheet_name, rows in sheets.items():
                pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name[:31], index=False)
        return output.getvalue()

    @staticmethod
    def export_to_csv(records: List[PerformanceRecord]) -> bytes:
        flat_records = [ReportExporter.flatten_record(record) for record in records]
        output = io.BytesIO()
        pd.DataFrame(flat_records).to_csv(output, index=False, encoding="utf-8-sig")
        return output.getvalue()

    @staticmethod
    def export_report(
        *,
        title: str,
        metadata: dict[str, Any],
        sheets: dict[str, list[dict[str, Any]]],
        output_format: str,
    ) -> tuple[bytes, str, str]:
        normalized = (output_format or "pptx").lower()
        if normalized == "pdf":
            return ReportExporter._export_pdf(title=title, metadata=metadata, sheets=sheets), "application/pdf", ".pdf"
        return (
            ReportExporter._export_pptx(title=title, metadata=metadata, sheets=sheets),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx",
        )

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, bool):
            text = "Yes" if value else "No"
        else:
            text = str(value)
        text = text.replace("\r", " ").replace("\n", " ")
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = " ".join(text.split())
        return text or "N/A"

    @staticmethod
    def _report_lines(title: str, metadata: dict[str, Any], sheets: dict[str, list[dict[str, Any]]]) -> list[str]:
        lines = [ReportExporter._clean_text(title), ""]
        for key, value in metadata.items():
            lines.append(f"{key}: {ReportExporter._clean_text(value)}")
        for section_name, rows in sheets.items():
            lines.extend(["", section_name])
            if not rows:
                lines.append("No matching rows.")
                continue
            for row in rows[:6]:
                parts = []
                for row_key, row_value in list(row.items())[:5]:
                    parts.append(f"{row_key}: {ReportExporter._clean_text(row_value)}")
                suffix = " ..." if len(row) > 5 else ""
                lines.append(" - " + " | ".join(parts) + suffix)
        return lines

    @staticmethod
    def _wrap_lines(lines: Iterable[str], width: int) -> list[str]:
        wrapped: list[str] = []
        for line in lines:
            if not line:
                wrapped.append("")
                continue
            wrapped.extend(textwrap.wrap(line, width=width, break_long_words=False, break_on_hyphens=False) or [line])
        return wrapped

    @staticmethod
    def _export_pdf(*, title: str, metadata: dict[str, Any], sheets: dict[str, list[dict[str, Any]]]) -> bytes:
        body_lines = ReportExporter._wrap_lines(ReportExporter._report_lines(title, metadata, sheets)[1:], width=92)
        page_chunks = [body_lines[index : index + 38] for index in range(0, len(body_lines), 38)] or [[]]

        page_count = len(page_chunks)
        font_id = 1
        content_ids = [2 + index * 2 for index in range(page_count)]
        page_ids = [content_id + 1 for content_id in content_ids]
        pages_id = 2 + page_count * 2
        catalog_id = pages_id + 1

        pdf_objects: dict[int, bytes] = {font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
        for index, lines in enumerate(page_chunks):
            content_id = content_ids[index]
            page_id = page_ids[index]
            content_stream = ReportExporter._pdf_content_stream(title=title, lines=lines).encode("utf-8")
            pdf_objects[content_id] = (
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("utf-8")
                + content_stream
                + b"\nendstream"
            )
            pdf_objects[page_id] = (
                "<< /Type /Page /Parent "
                f"{pages_id} 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("utf-8")
        pdf_objects[pages_id] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {page_count} >>".encode("utf-8")
        pdf_objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("utf-8")

        ordered = [
            f"{index} 0 obj\n".encode("utf-8") + pdf_objects[index] + b"\nendobj\n"
            for index in range(1, catalog_id + 1)
        ]

        output = io.BytesIO()
        output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for payload in ordered:
            offsets.append(output.tell())
            output.write(payload)
        xref_position = output.tell()
        output.write(f"xref\n0 {len(ordered) + 1}\n".encode("utf-8"))
        output.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
        output.write(
            (
                "trailer\n"
                f"<< /Size {len(ordered) + 1} /Root {catalog_id} 0 R >>\n"
                f"startxref\n{xref_position}\n%%EOF"
            ).encode("utf-8")
        )
        return output.getvalue()

    @staticmethod
    def _pdf_content_stream(*, title: str, lines: list[str]) -> str:
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        rendered = [
            "BT",
            "/F1 20 Tf",
            "1 0 0 1 50 740 Tm",
            f"({esc(ReportExporter._clean_text(title))}) Tj",
            "T*",
            "/F1 11 Tf",
            "14 TL",
        ]
        for line in lines:
            rendered.append(f"({esc(ReportExporter._clean_text(line))}) Tj")
            rendered.append("T*")
        rendered.append("ET")
        return "\n".join(rendered)

    @staticmethod
    def _export_pptx(*, title: str, metadata: dict[str, Any], sheets: dict[str, list[dict[str, Any]]]) -> bytes:
        body_lines = ReportExporter._wrap_lines(ReportExporter._report_lines(title, metadata, sheets)[1:], width=72)
        slide_chunks = [body_lines[index : index + 18] for index in range(0, len(body_lines), 18)] or [[]]

        output = io.BytesIO()
        with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", ReportExporter._pptx_content_types(len(slide_chunks)))
            archive.writestr("_rels/.rels", ReportExporter._pptx_root_rels())
            archive.writestr("docProps/core.xml", ReportExporter._pptx_core_props(title))
            archive.writestr("docProps/app.xml", ReportExporter._pptx_app_props(title, len(slide_chunks)))
            archive.writestr("ppt/presentation.xml", ReportExporter._pptx_presentation_xml(len(slide_chunks)))
            archive.writestr("ppt/_rels/presentation.xml.rels", ReportExporter._pptx_presentation_rels(len(slide_chunks)))
            archive.writestr("ppt/slideMasters/slideMaster1.xml", ReportExporter._pptx_slide_master())
            archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", ReportExporter._pptx_slide_master_rels())
            archive.writestr("ppt/slideLayouts/slideLayout1.xml", ReportExporter._pptx_slide_layout())
            archive.writestr("ppt/theme/theme1.xml", ReportExporter._pptx_theme())
            for index, lines in enumerate(slide_chunks, start=1):
                archive.writestr(f"ppt/slides/slide{index}.xml", ReportExporter._pptx_slide_xml(title, lines))
                archive.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", ReportExporter._pptx_slide_rels())
        return output.getvalue()

    @staticmethod
    def _pptx_content_types(slide_count: int) -> str:
        slide_overrides = "".join(
            f'<Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            for index in range(1, slide_count + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            f"{slide_overrides}"
            '</Types>'
        )

    @staticmethod
    def _pptx_root_rels() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _pptx_core_props(title: str) -> str:
        created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        clean_title = xml_escape(ReportExporter._clean_text(title))
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{clean_title}</dc:title>'
            '<dc:creator>PMS Dashboard</dc:creator>'
            '<cp:lastModifiedBy>PMS Dashboard</cp:lastModifiedBy>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
            '</cp:coreProperties>'
        )

    @staticmethod
    def _pptx_app_props(title: str, slide_count: int) -> str:
        clean_title = xml_escape(ReportExporter._clean_text(title))
        slide_entries = ''.join(f'<vt:lpstr>Slide {index}</vt:lpstr>' for index in range(1, slide_count + 1))
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            f'<Application>{clean_title}</Application>'
            f'<PresentationFormat>{clean_title}</PresentationFormat>'
            f'<Slides>{slide_count}</Slides>'
            '<Notes>0</Notes>'
            '<HiddenSlides>0</HiddenSlides>'
            '<MMClips>0</MMClips>'
            '<ScaleCrop>false</ScaleCrop>'
            f'<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Slides</vt:lpstr></vt:variant><vt:variant><vt:i4>{slide_count}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
            f'<TitlesOfParts><vt:vector size="{slide_count}" baseType="lpstr">{slide_entries}</vt:vector></TitlesOfParts>'
            '<Company>PMS Dashboard</Company>'
            '<LinksUpToDate>false</LinksUpToDate>'
            '<SharedDoc>false</SharedDoc>'
            '<HyperlinksChanged>false</HyperlinksChanged>'
            '<AppVersion>17.0000</AppVersion>'
            '</Properties>'
        )

    @staticmethod
    def _pptx_presentation_xml(slide_count: int) -> str:
        slides = ''.join(f'<p:sldId id="{256 + index}" r:id="rId{index}"/>' for index in range(1, slide_count + 1))
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdMaster1"/></p:sldMasterIdLst>'
            f'<p:sldIdLst>{slides}</p:sldIdLst>'
            '<p:sldSz cx="9144000" cy="6858000" type="screen4x3"/>'
            '<p:notesSz cx="6858000" cy="9144000"/>'
            '</p:presentation>'
        )

    @staticmethod
    def _pptx_presentation_rels(slide_count: int) -> str:
        slide_rels = ''.join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
            for index in range(1, slide_count + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdMaster1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            f'{slide_rels}'
            '</Relationships>'
        )

    @staticmethod
    def _pptx_slide_master() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            '</p:sldMaster>'
        )

    @staticmethod
    def _pptx_slide_master_rels() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _pptx_slide_layout() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sldLayout>'
        )

    @staticmethod
    def _pptx_theme() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="PMS Dashboard Theme">'
            '<a:themeElements>'
            '<a:clrScheme name="PMS Dashboard">'
            '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="1F2937"/></a:dk2>'
            '<a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>'
            '<a:accent1><a:srgbClr val="2563EB"/></a:accent1>'
            '<a:accent2><a:srgbClr val="10B981"/></a:accent2>'
            '<a:accent3><a:srgbClr val="F59E0B"/></a:accent3>'
            '<a:accent4><a:srgbClr val="8B5CF6"/></a:accent4>'
            '<a:accent5><a:srgbClr val="14B8A6"/></a:accent5>'
            '<a:accent6><a:srgbClr val="EF4444"/></a:accent6>'
            '<a:hlink><a:srgbClr val="2563EB"/></a:hlink>'
            '<a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>'
            '</a:clrScheme>'
            '<a:fontScheme name="PMS Dashboard">'
            '<a:majorFont><a:latin typeface="Aptos"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Aptos"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
            '</a:fontScheme>'
            '<a:fmtScheme name="PMS Dashboard">'
            '<a:fillStyleLst>'
            '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="accent2"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="accent3"/></a:solidFill>'
            '</a:fillStyleLst>'
            '<a:lnStyleLst>'
            '<a:ln w="9525"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln>'
            '<a:ln w="9525"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:ln>'
            '<a:ln w="9525"><a:solidFill><a:schemeClr val="accent3"/></a:solidFill></a:ln>'
            '</a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst>'
            '<a:solidFill><a:schemeClr val="lt1"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="lt2"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="dk2"/></a:solidFill>'
            '</a:bgFillStyleLst>'
            '</a:fmtScheme>'
            '</a:themeElements>'
            '</a:theme>'
        )

    @staticmethod
    def _pptx_slide_xml(title: str, body_lines: list[str]) -> str:
        title_text = xml_escape(ReportExporter._clean_text(title))
        body_text = "".join(
            f'<a:p><a:r><a:rPr lang="en-US" sz="1700"/><a:t>{xml_escape(ReportExporter._clean_text(line))}</a:t></a:r></a:p>'
            if line
            else "<a:p/>"
            for line in body_lines
        ) or "<a:p/>"
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp>'
            '<p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="457200" y="304800"/><a:ext cx="8229600" cy="685800"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="2800" b="1"/><a:t>{title_text}</a:t></a:r></a:p></p:txBody>'
            '</p:sp>'
            '<p:sp>'
            '<p:nvSpPr><p:cNvPr id="3" name="Body 2"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="457200" y="1270000"/><a:ext cx="8229600" cy="4876800"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{body_text}</p:txBody>'
            '</p:sp>'
            '</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
            '</p:sld>'
        )

    @staticmethod
    def _pptx_slide_rels() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '</Relationships>'
        )
