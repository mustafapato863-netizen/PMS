import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { EvaluationPeriodData, EvaluationRevision } from '../evaluationSettings';
import { EvaluationHistory, type EvaluationHistoryProps } from './EvaluationHistory';

const FULL = 'a'.repeat(32) + 'b'.repeat(32);

const HISTORY: EvaluationPeriodData['history'] = [
  { id: 'approved-july', status: 'approved', lines: [], version_number: 2, checksum: FULL, source_version_id: 'draft-june', month_name: 'July' },
  { id: 'draft-july', status: 'draft', lines: [], version_number: 3, checksum: 'sum-draft', month_name: 'July' },
];

const REVISIONS: EvaluationRevision[] = [
  { id: 'revision-1', versionId: 'draft-july', status: 'rolled_back', createdAt: '2026-07-20T00:00:00Z', affectedCount: 2, canRollback: false },
  { id: 'revision-2', versionId: 'approved-july', status: 'active', createdAt: '2026-07-21T00:00:00Z', affectedCount: 1, canRollback: true },
];

function props(overrides: Partial<EvaluationHistoryProps> = {}): EvaluationHistoryProps {
  return {
    history: HISTORY,
    revisions: REVISIONS,
    periodLoading: false,
    monthName: 'July',
    busy: false,
    onRequestRollback: vi.fn(),
    ...overrides,
  };
}

function setClipboard(value: unknown) {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

describe('EvaluationHistory timeline', () => {
  it('renders a History heading and one entry per version and per revision', () => {
    render(<EvaluationHistory {...props()} />);
    expect(screen.getByRole('heading', { name: 'History' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
    expect(screen.getByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText('Version 3')).toBeInTheDocument();
    expect(screen.getByText('Revision revision-1 · rolled_back · version draft-july · 2 records · 2026-07-20T00:00:00Z')).toBeInTheDocument();
  });

  it('keeps the entries in the order they were received', () => {
    render(<EvaluationHistory {...props()} />);
    const items = screen.getAllByRole('listitem').map((item) => item.textContent ?? '');
    expect(items[0]).toContain('Version 2');
    expect(items[1]).toContain('Version 3');
    expect(items[2]).toContain('revision-1');
    expect(items[3]).toContain('revision-2');
  });

  it('shows a short checksum by default and never the full 64-character value', () => {
    render(<EvaluationHistory {...props()} />);
    expect(screen.getByText('aaaaaaaa')).toBeInTheDocument();
    expect(screen.getByText('sum-draf')).toBeInTheDocument();
    expect(screen.queryByText(FULL)).not.toBeInTheDocument();
  });

  it('shows Rollback only on a revision that allows it', () => {
    render(<EvaluationHistory {...props()} />);
    const rollbacks = screen.getAllByRole('button', { name: 'Rollback' });
    expect(rollbacks).toHaveLength(1);
    const allowed = screen.getByText(/Revision revision-2/).closest('li');
    expect(allowed).not.toBeNull();
    expect(within(allowed as HTMLElement).getByRole('button', { name: 'Rollback' })).toBeInTheDocument();
  });

  it('passes the revision id to the existing rollback handler', () => {
    const onRequestRollback = vi.fn();
    render(<EvaluationHistory {...props({ onRequestRollback })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Rollback' }));
    expect(onRequestRollback).toHaveBeenCalledWith('revision-2');
  });

  it('disables Rollback while a request is busy', () => {
    render(<EvaluationHistory {...props({ busy: true })} />);
    expect(screen.getByRole('button', { name: 'Rollback' })).toBeDisabled();
  });

  it('names the source of a version when there is one, and not otherwise', () => {
    render(<EvaluationHistory {...props()} />);
    expect(screen.getByText('Built from draft-june')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Copy checksum for/ })).toHaveLength(2);
  });

  it('shows no copy action for a version without a checksum', () => {
    render(<EvaluationHistory {...props({ history: [{ ...HISTORY[0], checksum: null }], revisions: [] })} />);
    expect(screen.queryByRole('button', { name: /Copy checksum/ })).not.toBeInTheDocument();
  });

  it('shows the empty message when there are no versions and no revisions', () => {
    render(<EvaluationHistory {...props({ history: [], revisions: [] })} />);
    expect(screen.getByText('No saved versions for this month.')).toBeInTheDocument();
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
  });

  it('shows the loading text and no entries while the month loads', () => {
    render(<EvaluationHistory {...props({ periodLoading: true })} />);
    expect(screen.getByText('Loading this month…')).toBeInTheDocument();
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
  });
});

describe('EvaluationHistory copy checksum', () => {
  afterEach(() => {
    setClipboard(undefined);
  });

  it('copies the full checksum and confirms with a short status', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    render(<EvaluationHistory {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy checksum for Version 2' }));
    expect(writeText).toHaveBeenCalledWith(FULL);
    expect(await screen.findByText('Copied')).toBeInTheDocument();
    expect(screen.queryByText(FULL)).not.toBeInTheDocument();
  });

  it('shows the full checksum once, with a short failure status, when the copy is refused', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
    render(<EvaluationHistory {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy checksum for Version 2' }));
    await waitFor(() => expect(screen.getByText(/Copy failed/)).toBeInTheDocument());
    expect(screen.getByText(FULL)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('takes the same failure path when the clipboard is unavailable', async () => {
    setClipboard(undefined);
    render(<EvaluationHistory {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy checksum for Version 3' }));
    expect(await screen.findByText(/Copy failed/)).toBeInTheDocument();
    expect(screen.getByText('sum-draft')).toBeInTheDocument();
  });
});
