import JSZip from 'jszip';
import type { PMSAction } from '../types';

export const CORRECTIVE_ACTION_TEMPLATE_URL = '/templates/Corrective_Action_Report.pptx';

export interface CorrectiveActionExportFilters {
  team: string;
  month: string;
  type: string;
}

type CardSlot = {
  badge: number;
  badgeText: number;
  name: number;
  metadata: number;
  action: number;
  rootCause: number;
  date: number;
  owner: number;
};

const CARD_SLOTS: CardSlot[] = [
  { badge: 6, badgeText: 7, name: 8, metadata: 9, action: 10, rootCause: 12, date: 14, owner: 16 },
  { badge: 18, badgeText: 19, name: 20, metadata: 21, action: 22, rootCause: 24, date: 26, owner: 28 },
  { badge: 30, badgeText: 31, name: 32, metadata: 33, action: 34, rootCause: 36, date: 38, owner: 40 },
  { badge: 42, badgeText: 43, name: 44, metadata: 45, action: 46, rootCause: 48, date: 50, owner: 52 },
];

// The source template already uses rId1-rId7 for its master, notes, theme,
// and presentation parts. Keep generated slide relationships outside that
// range so PowerPoint's package relationship IDs stay unique.
const SLIDE_RELATIONSHIP_BASE = 100;

const ACTION_STYLE: Record<string, { fill: string; text: string }> = {
  Training: { fill: 'DBEAFE', text: '1D4ED8' },
  Reward: { fill: 'D1FAE5', text: '047857' },
  PIP: { fill: 'FCE7F3', text: 'BE123C' },
  Monitor: { fill: 'FEF3C7', text: 'B45309' },
  Coaching: { fill: 'F3E8FF', text: '7C3AED' },
};

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function compactText(value: unknown, maxLength: number): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return 'Not provided';
  return text.length > maxLength ? `${text.slice(0, maxLength - 1).trimEnd()}…` : text;
}

function formatActionDate(value: string): string {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

function cardShape(xml: string, shapeId: number): { start: number; end: number; value: string } | null {
  const marker = `<p:cNvPr id="${shapeId}"`;
  const markerIndex = xml.indexOf(marker);
  if (markerIndex < 0) return null;
  const start = xml.lastIndexOf('<p:sp>', markerIndex);
  const closing = xml.indexOf('</p:sp>', markerIndex);
  if (start < 0 || closing < 0) return null;
  const end = closing + '</p:sp>'.length;
  return { start, end, value: xml.slice(start, end) };
}

function replaceShapeText(xml: string, shapeId: number, value: string, run: 'first' | 'last' = 'first'): string {
  const shape = cardShape(xml, shapeId);
  if (!shape) return xml;
  const textRuns = [...shape.value.matchAll(/<a:t>[\s\S]*?<\/a:t>/g)];
  if (!textRuns.length) return xml;
  const target = textRuns[run === 'last' ? textRuns.length - 1 : 0];
  const replacement = `<a:t>${escapeXml(value)}</a:t>`;
  const nextShape = `${shape.value.slice(0, target.index)}${replacement}${shape.value.slice((target.index || 0) + target[0].length)}`;
  return `${xml.slice(0, shape.start)}${nextShape}${xml.slice(shape.end)}`;
}

function replaceShapeColors(xml: string, shapeId: number, color: string): string {
  const shape = cardShape(xml, shapeId);
  if (!shape) return xml;
  const nextShape = shape.value.replace(/(<a:srgbClr val=")[0-9A-Fa-f]{6}("\/>)/g, `$1${color}$2`);
  return `${xml.slice(0, shape.start)}${nextShape}${xml.slice(shape.end)}`;
}

function replaceTextColor(xml: string, shapeId: number, color: string): string {
  const shape = cardShape(xml, shapeId);
  if (!shape) return xml;
  const nextShape = shape.value.replace(/(<a:srgbClr val=")[0-9A-Fa-f]{6}("\/>)/, `$1${color}$2`);
  return `${xml.slice(0, shape.start)}${nextShape}${xml.slice(shape.end)}`;
}

function setSlideNumber(xml: string, pageNumber: number): string {
  const pageLabel = String(pageNumber).padStart(2, '0');
  const next = xml.replace(/(<a:fld[^>]*type="slidenum"[^>]*>[\s\S]*?<a:t>)[^<]*(<\/a:t>)/, `$1${pageLabel}$2`);
  return next === xml ? replaceShapeText(xml, 54, pageLabel) : next;
}

function replaceCard(xml: string, slot: CardSlot, action: PMSAction): string {
  const style = ACTION_STYLE[action.action_type] || ACTION_STYLE.Coaching;
  let next = replaceShapeText(xml, slot.badgeText, String(action.action_type || 'Action').toUpperCase());
  next = replaceShapeColors(next, slot.badge, style.fill);
  next = replaceTextColor(next, slot.badgeText, style.text);
  next = replaceShapeText(next, slot.name, compactText(action.employee_name, 42));
  next = replaceShapeText(next, slot.metadata, `${compactText(action.team || 'Unassigned team', 42)} • ${compactText(action.employee_id, 18)}`);
  next = replaceShapeText(next, slot.action, compactText(action.action_text, 190));
  next = replaceShapeText(next, slot.rootCause, compactText(action.root_cause_note, 150), 'last');
  next = replaceShapeText(next, slot.date, `${compactText(action.month, 18)} – ${formatActionDate(action.created_at)}`);
  next = replaceShapeText(next, slot.owner, `By ${compactText(action.created_by || 'Unknown', 22)}`);
  return next;
}

function clearCard(xml: string, slot: CardSlot): string {
  let next = replaceShapeText(xml, slot.badgeText, '—');
  next = replaceShapeColors(next, slot.badge, 'E2E8F0');
  next = replaceTextColor(next, slot.badgeText, '64748B');
  next = replaceShapeText(next, slot.name, 'No additional action');
  next = replaceShapeText(next, slot.metadata, 'No matching record');
  next = replaceShapeText(next, slot.action, 'No additional action in this scope.');
  next = replaceShapeText(next, slot.rootCause, 'No data', 'last');
  next = replaceShapeText(next, slot.date, '—');
  next = replaceShapeText(next, slot.owner, '—');
  return next;
}

function updateSlide(xml: string, actions: PMSAction[], pageNumber: number, filters: CorrectiveActionExportFilters): string {
  let next = xml.replace(/(<p:cSld name=")([^"]*)/i, `$1Slide ${pageNumber}`);
  next = setSlideNumber(next, pageNumber);
  next = replaceShapeText(next, 4, `Current actions • ${filters.month} • ${filters.team} • ${filters.type}`);
  const pageActions = actions.length ? actions : [{
    id: 'empty', employee_id: '', employee_name: 'No corrective actions found', team: filters.team, month: filters.month,
    action_type: 'Monitor', action_text: 'No actions matched the selected filters. Try another team, month, or action type.', root_cause_note: 'No matching rows',
    created_by: 'System', created_at: new Date().toISOString(), synced: true,
  } as PMSAction];
  CARD_SLOTS.forEach((slot, index) => {
    const action = pageActions[index];
    next = action ? replaceCard(next, slot, action) : clearCard(next, slot);
  });
  return next;
}

function duplicateRelationship(xml: string, pageNumber: number): string {
  return xml.replaceAll('slide1', `slide${pageNumber}`).replaceAll('Slide 3', `Slide ${pageNumber}`);
}

function updatePresentation(presentationXml: string, pageCount: number): string {
  const slides = Array.from({ length: pageCount }, (_, index) => `<p:sldId id="${258 + index}" r:id="rId${SLIDE_RELATIONSHIP_BASE + index}"/>`).join('');
  return presentationXml.replace(/<p:sldIdLst>[\s\S]*?<\/p:sldIdLst>/, `<p:sldIdLst>${slides}</p:sldIdLst>`);
}

function updatePresentationRelationships(xml: string, pageCount: number): string {
  const relationships = Array.from({ length: pageCount }, (_, index) => `<Relationship Id="rId${SLIDE_RELATIONSHIP_BASE + index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${index + 1}.xml"/>`).join('');
  return xml.replace(/<Relationships[^>]*>[\s\S]*?<\/Relationships>/, (block) => {
    const opening = block.slice(0, block.indexOf('>') + 1);
    const retained = [...block.matchAll(/<Relationship\b[^>]*\/>/g)]
      .map((match) => match[0])
      .filter((relationship) => !relationship.includes('/relationships/slide"'))
      .join('');
    return `${opening}${retained}${relationships}</Relationships>`;
  });
}

function updateContentTypes(xml: string, pageCount: number): string {
  const overrides = Array.from({ length: pageCount - 1 }, (_, index) => {
    const page = index + 2;
    return `<Override PartName="/ppt/slides/slide${page}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/><Override PartName="/ppt/notesSlides/notesSlide${page}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>`;
  }).join('');
  return xml.replace('</Types>', `${overrides}</Types>`);
}

export async function buildCorrectiveActionsPowerPoint(
  actions: PMSAction[],
  filters: CorrectiveActionExportFilters,
  templateUrl = CORRECTIVE_ACTION_TEMPLATE_URL,
): Promise<Blob> {
  const response = await fetch(templateUrl);
  if (!response.ok) throw new Error(`PowerPoint template could not be loaded (${response.status}).`);
  const template = await response.arrayBuffer();
  const zip = await JSZip.loadAsync(template);
  const slideTemplate = await zip.file('ppt/slides/slide1.xml')?.async('string');
  const slideRelsTemplate = await zip.file('ppt/slides/_rels/slide1.xml.rels')?.async('string');
  const notesTemplate = await zip.file('ppt/notesSlides/notesSlide1.xml')?.async('string');
  const notesRelsTemplate = await zip.file('ppt/notesSlides/_rels/notesSlide1.xml.rels')?.async('string');
  const presentationTemplate = await zip.file('ppt/presentation.xml')?.async('string');
  const presentationRelsTemplate = await zip.file('ppt/_rels/presentation.xml.rels')?.async('string');
  const contentTypesTemplate = await zip.file('[Content_Types].xml')?.async('string');
  if (!slideTemplate || !slideRelsTemplate || !notesTemplate || !notesRelsTemplate || !presentationTemplate || !presentationRelsTemplate || !contentTypesTemplate) {
    throw new Error('The PowerPoint template is missing required slide parts.');
  }

  const pageCount = Math.max(1, Math.ceil(actions.length / CARD_SLOTS.length));
  for (let page = 1; page <= pageCount; page += 1) {
    const pageActions = actions.slice((page - 1) * CARD_SLOTS.length, page * CARD_SLOTS.length);
    zip.file(`ppt/slides/slide${page}.xml`, updateSlide(slideTemplate, pageActions, page, filters));
    zip.file(`ppt/notesSlides/notesSlide${page}.xml`, setSlideNumber(notesTemplate, page));
    if (page > 1) {
      zip.file(`ppt/slides/_rels/slide${page}.xml.rels`, duplicateRelationship(slideRelsTemplate, page));
      zip.file(`ppt/notesSlides/_rels/notesSlide${page}.xml.rels`, duplicateRelationship(notesRelsTemplate, page));
    }
  }
  zip.file('ppt/presentation.xml', updatePresentation(presentationTemplate, pageCount));
  zip.file('ppt/_rels/presentation.xml.rels', updatePresentationRelationships(presentationRelsTemplate, pageCount));
  zip.file('[Content_Types].xml', updateContentTypes(contentTypesTemplate, pageCount));
  return zip.generateAsync({ type: 'blob', mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' });
}

export async function downloadCorrectiveActionsPowerPoint(actions: PMSAction[], filters: CorrectiveActionExportFilters): Promise<void> {
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
