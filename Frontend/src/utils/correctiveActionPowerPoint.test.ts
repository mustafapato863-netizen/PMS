import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import JSZip from 'jszip';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PMSAction } from '../types';
import { buildCorrectiveActionsPowerPoint } from './correctiveActionPowerPoint';

const templatePath = join(process.cwd(), 'public', 'templates', 'Corrective_Action_Report.pptx');

const actions: PMSAction[] = Array.from({ length: 5 }, (_, index) => ({
  id: `action-${index + 1}`,
  employee_id: `EMP-${index + 1}`,
  employee_name: `Employee ${index + 1}`,
  team: index % 2 ? 'Outbound' : 'Inbound',
  month: 'June',
  action_type: index % 2 ? 'Coaching' : 'Training',
  action_text: `Action detail ${index + 1}`,
  root_cause_note: `Root cause ${index + 1}`,
  created_by: 'Admin',
  created_at: '2026-06-15T10:00:00Z',
  synced: true,
}));

describe('corrective action PowerPoint export', () => {
  afterEach(() => vi.restoreAllMocks());

  it('duplicates the template layout for additional action pages and injects action data', async () => {
    const template = await readFile(templatePath);
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      arrayBuffer: async () => new Uint8Array(template),
    })));

    const blob = await buildCorrectiveActionsPowerPoint(actions, { team: 'All teams', month: 'June', type: 'All types' });
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    const secondSlide = await zip.file('ppt/slides/slide2.xml')?.async('string');
    const presentationRelationships = await zip.file('ppt/_rels/presentation.xml.rels')?.async('string');

    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.presentationml.presentation');
    expect(secondSlide).toContain('Employee 5');
    expect(secondSlide).toContain('Action detail 5');
    expect(secondSlide).toContain('Slide 2');
    expect(await zip.file('ppt/notesSlides/notesSlide2.xml')?.async('string')).toContain('2');
    expect(presentationRelationships).toContain('Target="slides/slide2.xml"');
    expect(presentationRelationships).not.toContain('slide3.xml');

    if (process.env.WRITE_PPTX === '1') {
      await writeFile(join(process.cwd(), '..', '.tmp', 'corrective-action-pptx', 'corrective-actions-sample.pptx'), Buffer.from(await blob.arrayBuffer()));
    }
  });
});
