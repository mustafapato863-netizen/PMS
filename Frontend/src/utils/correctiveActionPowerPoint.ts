/**
 * correctiveActionPowerPoint.ts
 * Generates a high-fidelity PowerPoint presentation from scratch (no external template)
 * that perfectly mirrors the system's UI card layout:
 * - Enterprise dark navy header with filters and pagination
 * - Zero vertical clipping (fits 16:9 widescreen with generous breathing margins)
 * - True horizontal centering with 2-card side-by-side grid
 * - White cards with subtle 12px rounded corners and soft borders
 * - Aligned top row: bold employee name and rounded badge pill
 * - Preserved structured action text paragraphs with bold markdown parsing
 * - Soft amber root-cause note box with inline bold label
 * - Crisp footer with calendar date and owner attribution
 * - Compliant OpenXML schema with theme1.xml and masterClrMapping to guarantee 0 corruption warnings
 */
import JSZip from 'jszip';
import type { PMSAction } from '../types';
import { THEME_XML } from './pptxTheme';

export const CORRECTIVE_ACTION_TEMPLATE_URL = '/templates/Corrective_Action_Report.pptx';

export interface CorrectiveActionExportFilters {
  team: string;
  month: string;
  type: string;
}

// ─── Colour palette (hex without #) ─────────────────────────────────────────
const BADGE: Record<string, { bg: string; fg: string }> = {
  Training: { bg: 'DBEAFE', fg: '1D4ED8' },
  Reward:   { bg: 'D1FAE5', fg: '047857' },
  PIP:      { bg: 'FCE7F3', fg: 'BE123C' },
  Monitor:  { bg: 'FEF3C7', fg: 'B45309' },
  Coaching: { bg: 'F3E8FF', fg: '7C3AED' },
};

// ─── Slide dimensions: 16:9 widescreen ──────────────────────────────────────
// PowerPoint default: 10 in × 5.625 in → 9144000 × 5143500 EMU
const SLIDE_CX = 9144000;
const SLIDE_CY = 5143500;
const SLIDE_W_IN = 10.0;

// ─── Layout Geometry (inches) ────────────────────────────────────────────────
// Header bar
const TOP_BAR_H = 0.65;

// Cards geometry: centered horizontally and vertically with 0.165 in bottom safety margin
const CARD_W    = 4.64;
const CARD_H    = 4.68;
const CARD_Y    = 0.78;
const CARD_PAD  = 0.22;
const COL_GAP   = 0.24;

// Two column X coordinates: left = 0.24 in, right = 5.12 in (Left margin = 0.24, Right margin = 0.24)
const COLS = [0.24, 0.24 + CARD_W + COL_GAP];

// ─── Helpers ─────────────────────────────────────────────────────────────────
const in2emu = (inches: number) => Math.round(inches * 914400);
const pt2emu = (pt: number) => Math.round(pt * 12700);

function x(val: string): string {
  return val
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function trunc(val: unknown, max: number): string {
  const s = String(val || '').trim() || 'Not provided';
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s;
}

function fmtDate(val: string): string {
  if (!val) return 'Date unavailable';
  const d = new Date(val);
  return isNaN(d.getTime()) ? val : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(d);
}

// ─── Low-level XML builders ───────────────────────────────────────────────────

function xfrm(xIn: number, yIn: number, wIn: number, hIn: number, rot = 0): string {
  const r = rot ? ` rot="${rot}"` : '';
  return `<a:xfrm${r}><a:off x="${in2emu(xIn)}" y="${in2emu(yIn)}"/><a:ext cx="${in2emu(wIn)}" cy="${in2emu(hIn)}"/></a:xfrm>`;
}

function solidFill(hex: string): string {
  return `<a:solidFill><a:srgbClr val="${hex}"/></a:solidFill>`;
}

function noFill(): string {
  return '<a:noFill/>';
}

function ln(hex?: string, wPt = 0.5): string {
  if (!hex) return '<a:ln><a:noFill/></a:ln>';
  return `<a:ln w="${pt2emu(wPt)}">${solidFill(hex)}</a:ln>`;
}

/** Build an OpenXML run with explicit Segoe UI typeface */
function run(
  text: string,
  opts: { bold?: boolean; szPt?: number; color?: string; italic?: boolean } = {}
): string {
  const { bold = false, szPt = 10, color = '1E293B', italic = false } = opts;
  const sz = Math.round(szPt * 100);
  return `<a:r>
    <a:rPr lang="en-US" sz="${sz}" b="${bold ? 1 : 0}" i="${italic ? 1 : 0}" dirty="0">
      ${solidFill(color)}
      <a:latin typeface="Segoe UI"/>
      <a:ea typeface="Segoe UI"/>
      <a:cs typeface="Segoe UI"/>
    </a:rPr>
    <a:t>${x(text)}</a:t>
  </a:r>`;
}

/** Single paragraph with one run */
function para(
  text: string,
  opts: {
    bold?: boolean;
    szPt?: number;
    color?: string;
    align?: 'l' | 'ctr' | 'r';
    italic?: boolean;
    spcBefPt?: number;
  } = {}
): string {
  const { align = 'l', spcBefPt } = opts;
  const spcBefEl = spcBefPt !== undefined ? `<a:spcBef><a:spcPts val="${Math.round(spcBefPt * 100)}"/></a:spcBef>` : '';
  return `<a:p>
    <a:pPr algn="${align}">${spcBefEl}</a:pPr>
    ${run(text, opts)}
  </a:p>`;
}

/** Paragraph with multiple inline runs (e.g. bold label + normal value) */
function multiRunPara(
  runs: Array<{ text: string; bold?: boolean; szPt?: number; color?: string; italic?: boolean }>,
  opts: { align?: 'l' | 'ctr' | 'r'; spcBefPt?: number } = {}
): string {
  const { align = 'l', spcBefPt } = opts;
  const spcBefEl = spcBefPt !== undefined ? `<a:spcBef><a:spcPts val="${Math.round(spcBefPt * 100)}"/></a:spcBef>` : '';
  const runsXml = runs.map((r) => run(r.text, r)).join('');
  return `<a:p>
    <a:pPr algn="${align}">${spcBefEl}</a:pPr>
    ${runsXml}
  </a:p>`;
}

/** Build a <p:sp> shape */
function sp(
  id: number,
  name: string,
  xIn: number, yIn: number, wIn: number, hIn: number,
  bodyXml: string,
  opts: {
    fill?: string;
    noFill?: boolean;
    borderHex?: string;
    roundAdj?: number;    // 0-50000, set for rounded rect
    anchor?: 't' | 'm' | 'b';
    lInsIn?: number;
    rInsIn?: number;
    tInsIn?: number;
    bInsIn?: number;
    autofit?: boolean;
  } = {}
): string {
  const fillEl = opts.noFill ? noFill() : solidFill(opts.fill || 'FFFFFF');
  const lineEl = ln(opts.borderHex);
  const prstGeom = opts.roundAdj !== undefined
    ? `<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val ${opts.roundAdj}"/></a:avLst></a:prstGeom>`
    : `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>`;

  const lIns = in2emu(opts.lInsIn ?? 0.08);
  const rIns = in2emu(opts.rInsIn ?? 0.08);
  const tIns = in2emu(opts.tInsIn ?? 0.05);
  const bIns = in2emu(opts.bInsIn ?? 0.05);
  const autofitEl = opts.autofit !== false ? '<a:normAutofit fontScale="90000"/>' : '';

  return `<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="${id}" name="${name}"/>
    <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    ${xfrm(xIn, yIn, wIn, hIn)}
    ${prstGeom}
    ${fillEl}
    ${lineEl}
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" lIns="${lIns}" rIns="${rIns}" tIns="${tIns}" bIns="${bIns}" anchor="${opts.anchor ?? 't'}">${autofitEl}</a:bodyPr>
    <a:lstStyle/>
    ${bodyXml}
  </p:txBody>
</p:sp>`;
}

/** Parses action text into structured paragraphs with bold markdown support */
function buildActionTextParagraphs(rawText: string): string {
  const cleaned = String(rawText || '').trim() || 'No action details provided.';
  const lines = cleaned.split(/\r?\n/);
  const paragraphs: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) {
      continue;
    }

    // Give section headings or numbered steps slight breathing room
    const isSectionHeading = /^(Booking|AHT|Attend|Call|QA|Coaching|Training|\d+\.)/i.test(line) && line.length < 50 && !line.includes('. ');
    const spcBefPt = i > 0 ? (isSectionHeading ? 4 : 2) : 0;

    // Parse markdown **bold**
    const runs: Array<{ text: string; bold: boolean; color: string; szPt: number }> = [];
    const parts = line.split(/(\*\*[^*]+\*\*)/g);

    for (const part of parts) {
      if (!part) continue;
      if (part.startsWith('**') && part.endsWith('**')) {
        runs.push({
          text: part.slice(2, -2),
          bold: true,
          color: '0F172A',
          szPt: 8.5,
        });
      } else {
        runs.push({
          text: part,
          bold: isSectionHeading,
          color: isSectionHeading ? '0F172A' : '334155',
          szPt: 8.5,
        });
      }
    }

    paragraphs.push(multiRunPara(runs, { align: 'l', spcBefPt }));
  }

  return paragraphs.length > 0 ? paragraphs.join('\n') : para('No action details provided.', { szPt: 8.5, color: '64748B' });
}

// ─── Card Builder ─────────────────────────────────────────────────────────────

/** Build one action card matching the UI card layout */
function buildCard(action: PMSAction, cardX: number, cardY: number, baseId: number): string {
  const style = BADGE[action.action_type] || BADGE.Coaching;

  const iX = cardX + CARD_PAD;
  const iW = CARD_W - CARD_PAD * 2;

  // Top header row: Name on left, Badge pill on right
  const nameY    = cardY + 0.18;
  const badgeY   = cardY + 0.18;
  const BADGE_W  = 0.95;
  const BADGE_H  = 0.26;
  const badgeX   = cardX + CARD_W - CARD_PAD - BADGE_W;
  const nameW    = iW - BADGE_W - 0.12;

  // Subtitle line (Team · ID)
  const metaY    = cardY + 0.50;

  // Action text box
  const actionY  = cardY + 0.78;
  const hasRc    = Boolean(action.root_cause_note && action.root_cause_note.trim());
  const actionH  = hasRc ? 2.45 : 3.25;

  // Root-cause note box (amber)
  const RC_H     = 0.70;
  const RC_Y     = cardY + 3.42;

  // Footer row (Date & Owner)
  const footerY  = cardY + CARD_H - 0.38;

  const shapes: string[] = [
    // Card background: clean white with subtle 12px rounded corners and soft border
    sp(baseId + 0, `card-bg-${baseId}`, cardX, cardY, CARD_W, CARD_H, '<a:p/>',
      { fill: 'FFFFFF', borderHex: 'E2E8F0', roundAdj: 3000, autofit: false }),

    // Employee name: bold title on the left
    sp(baseId + 1, `name-${baseId}`, iX, nameY, nameW, 0.30,
      para(trunc(action.employee_name || 'Unknown employee', 50), { bold: true, szPt: 13, color: '0F172A' }),
      { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 }),

    // Badge pill: right aligned in top row
    sp(baseId + 2, `badge-${baseId}`, badgeX, badgeY, BADGE_W, BADGE_H,
      para(trunc(action.action_type, 12).toUpperCase(), { bold: true, szPt: 7.5, color: style.fg, align: 'ctr' }),
      { fill: style.bg, roundAdj: 50000, tInsIn: 0.04, bInsIn: 0.04, lInsIn: 0.04, rInsIn: 0.04 }),

    // Meta line (Team · ID)
    sp(baseId + 3, `meta-${baseId}`, iX, metaY, iW, 0.22,
      para(`${trunc(action.team || 'Unassigned team', 30)} · ${trunc(action.employee_id, 16)}`, { szPt: 9, color: '64748B' }),
      { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 }),

    // Action text: preserved paragraphs and formatted runs
    sp(baseId + 4, `action-${baseId}`, iX, actionY, iW, actionH,
      buildActionTextParagraphs(action.action_text),
      { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0.02, bInsIn: 0.02 }),
  ];

  // Root-cause note box (amber pill) - only rendered if present
  if (hasRc) {
    shapes.push(
      sp(baseId + 5, `rc-box-${baseId}`, iX, RC_Y, iW, RC_H,
        multiRunPara([
          { text: 'Root-cause note: ', bold: true, szPt: 8, color: 'B45309' },
          { text: trunc(action.root_cause_note, 220), bold: false, szPt: 8, color: '92400E' },
        ]),
        { fill: 'FFFBEB', borderHex: 'FDE68A', roundAdj: 3500, tInsIn: 0.08, bInsIn: 0.08, lInsIn: 0.12, rInsIn: 0.12 })
    );
  }

  // Footer: Date (left)
  shapes.push(
    sp(baseId + 6, `date-${baseId}`, iX, footerY, iW * 0.52, 0.22,
      para(`📅 ${trunc(action.month, 12)} · ${fmtDate(action.created_at)}`, { szPt: 8, color: '64748B' }),
      { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 })
  );

  // Footer: Owner (right)
  shapes.push(
    sp(baseId + 7, `owner-${baseId}`, cardX + CARD_W * 0.45, footerY, CARD_W * 0.55 - CARD_PAD, 0.22,
      para(`👤 By ${trunc(action.created_by || 'Admin', 26)}`, { szPt: 8, color: '64748B', align: 'r' }),
      { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 })
  );

  return shapes.join('\n');
}

// ─── Slide XML ────────────────────────────────────────────────────────────────

function buildSlideXml(
  slideActions: PMSAction[],
  page: number,
  pageCount: number,
  filters: CorrectiveActionExportFilters,
): string {
  const filterLine = [
    filters.month !== 'All months' ? filters.month : '',
    filters.team  !== 'All teams'  ? filters.team  : '',
    filters.type  !== 'All types'  ? filters.type  : '',
  ].filter(Boolean).join(' · ') || 'All Actions';

  // Header bar (dark navy)
  const header = sp(2, 'header', 0, 0, SLIDE_W_IN, TOP_BAR_H, '<a:p/>', { fill: '0F172A', autofit: false });
  const headerLine = sp(3, 'header-line', 0, TOP_BAR_H - 0.01, SLIDE_W_IN, 0.01, '<a:p/>', { fill: '1E293B', autofit: false });

  // Title text in header
  const title = sp(4, 'title', 0.24, 0.10, 6.5, 0.30,
    para('Corrective Actions Report', { bold: true, szPt: 15, color: 'FFFFFF' }),
    { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 });

  // Filter subtitle in header
  const subtitle = sp(5, 'subtitle', 0.24, 0.38, 6.5, 0.20,
    para(filterLine, { szPt: 8.5, color: '94A3B8' }),
    { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 });

  // Page number right side of header
  const pageNum = sp(6, 'page-num', 8.0, 0.20, 1.76, 0.30,
    para(`${String(page).padStart(2, '0')} / ${String(pageCount).padStart(2, '0')}`,
      { szPt: 9.5, color: '94A3B8', align: 'r' }),
    { noFill: true, lInsIn: 0, rInsIn: 0, tInsIn: 0, bInsIn: 0 });

  // Cards — up to 2 per slide (left + right). If only 1 card on the slide, center it!
  const cards = slideActions.map((action, i) => {
    const colX = slideActions.length === 1 ? (SLIDE_W_IN - CARD_W) / 2 : COLS[i];
    return buildCard(action, colX, CARD_Y, 10 + i * 20);
  }).join('\n');

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld name="Slide ${page}">
    <p:bg>
      <p:bgPr>${solidFill('F8FAFC')}<a:effectLst/></p:bgPr>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="${SLIDE_CX}" cy="${SLIDE_CY}"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="${SLIDE_CX}" cy="${SLIDE_CY}"/>
        </a:xfrm>
      </p:grpSpPr>
      ${header}
      ${headerLine}
      ${title}
      ${subtitle}
      ${pageNum}
      ${cards}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>`;
}

// ─── Package XML files ────────────────────────────────────────────────────────

function buildRootRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>`;
}

function buildContentTypes(pageCount: number): string {
  const overrides = Array.from({ length: pageCount }, (_, i) =>
    `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`
  ).join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml"              ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml"             ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  ${overrides}
</Types>`;
}

function buildPresentation(pageCount: number): string {
  const ids = Array.from({ length: pageCount }, (_, i) =>
    `<p:sldId id="${256 + i}" r:id="rId${2 + i}"/>`).join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                saveSubsetFonts="1">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>${ids}</p:sldIdLst>
  <p:sldSz cx="${SLIDE_CX}" cy="${SLIDE_CY}" type="screen16x9"/>
  <p:notesSz cx="${SLIDE_CY}" cy="${SLIDE_CX}"/>
</p:presentation>`;
}

function buildPresentationRels(pageCount: number): string {
  const rels = Array.from({ length: pageCount }, (_, i) =>
    `<Relationship Id="rId${2 + i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${i + 1}.xml"/>`
  ).join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  ${rels}
</Relationships>`;
}

function buildTheme(): string {
  return THEME_XML;
}

function buildSlideMaster(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle><a:lvl1pPr><a:defRPr lang="en-US"><a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:defRPr></a:lvl1pPr></p:titleStyle>
    <p:bodyStyle><a:lvl1pPr><a:defRPr lang="en-US"><a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:defRPr></a:lvl1pPr></p:bodyStyle>
    <p:otherStyle><a:lvl1pPr><a:defRPr lang="en-US"><a:latin typeface="Segoe UI"/><a:ea typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:defRPr></a:lvl1pPr></p:otherStyle>
  </p:txStyles>
</p:sldMaster>`;
}

function buildSlideMasterRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>`;
}

function buildSlideLayout(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld name="Blank"><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>`;
}

function buildSlideLayoutRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>`;
}

function buildSlideRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>`;
}

// ─── Public API ───────────────────────────────────────────────────────────────

const CARDS_PER_SLIDE = 2; // 2 cards side-by-side per slide — matches UI layout

export async function buildCorrectiveActionsPowerPoint(
  actions: PMSAction[],
  filters: CorrectiveActionExportFilters,
): Promise<Blob> {
  const zip = new JSZip();
  const pageCount = Math.max(1, Math.ceil(actions.length / CARDS_PER_SLIDE));

  zip.file('_rels/.rels', buildRootRels());
  zip.file('[Content_Types].xml', buildContentTypes(pageCount));
  zip.file('ppt/presentation.xml', buildPresentation(pageCount));
  zip.file('ppt/_rels/presentation.xml.rels', buildPresentationRels(pageCount));
  zip.file('ppt/slideMasters/slideMaster1.xml', buildSlideMaster());
  zip.file('ppt/slideMasters/_rels/slideMaster1.xml.rels', buildSlideMasterRels());
  zip.file('ppt/theme/theme1.xml', buildTheme());
  zip.file('ppt/slideLayouts/slideLayout1.xml', buildSlideLayout());
  zip.file('ppt/slideLayouts/_rels/slideLayout1.xml.rels', buildSlideLayoutRels());

  for (let page = 1; page <= pageCount; page++) {
    const pageActions = actions.slice((page - 1) * CARDS_PER_SLIDE, page * CARDS_PER_SLIDE);
    zip.file(`ppt/slides/slide${page}.xml`, buildSlideXml(pageActions, page, pageCount, filters));
    zip.file(`ppt/slides/_rels/slide${page}.xml.rels`, buildSlideRels());
  }

  return zip.generateAsync({
    type: 'blob',
    mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
  });
}

export async function downloadCorrectiveActionsPowerPoint(
  actions: PMSAction[],
  filters: CorrectiveActionExportFilters,
): Promise<void> {
  const blob = await buildCorrectiveActionsPowerPoint(actions, filters);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `corrective-actions-${new Date().toISOString().slice(0, 10)}.pptx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
