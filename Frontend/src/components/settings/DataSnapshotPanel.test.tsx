import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DataSnapshotPanel, type SnapshotReport } from './DataSnapshotPanel';

const { fetchWithRole } = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole }),
}));

const counts = (incoming: number, created: number, existing = 0) => ({
  incoming,
  new: created,
  existing_ids: existing,
  skipped: existing,
  replaced: 0,
});

function report(overrides: Partial<SnapshotReport> = {}): SnapshotReport {
  return {
    dry_run: true,
    committed: false,
    importable: true,
    policy: 'skip',
    database_revision: null,
    snapshot_revision: null,
    tables: { teams: counts(2, 2), employees: counts(3, 3), actions: counts(0, 0) },
    totals: counts(5, 5),
    blocking_conflicts: [],
    blocking_conflict_count: 0,
    user_references: { matched: 1, cleared: {}, missing_accounts: [] },
    ...overrides,
  };
}

function ok(data: unknown) {
  return { ok: true, json: async () => ({ success: true, data }) };
}

async function chooseFileAndPolicy(user: ReturnType<typeof userEvent.setup>, container: HTMLElement, policy: RegExp = /Skip existing ids/) {
  const input = container.querySelector('input[type="file"]');
  expect(input).not.toBeNull();
  await user.upload(input as HTMLInputElement, new File(['{}'], 'snapshot.json', { type: 'application/json' }));
  await user.click(screen.getByRole('radio', { name: policy }));
}

describe('DataSnapshotPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    fetchWithRole.mockReset();
  });

  it('downloads the snapshot from the export endpoint', async () => {
    fetchWithRole.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['{}'], { type: 'application/json' }),
      headers: new Headers({ 'content-disposition': 'attachment; filename="pms-data-snapshot-20261015.json"' }),
    });
    const createObjectURL = vi.fn(() => 'blob:snapshot');
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const user = userEvent.setup();
    render(<DataSnapshotPanel />);

    await user.click(screen.getByRole('button', { name: 'Download snapshot' }));

    await waitFor(() => expect(fetchWithRole).toHaveBeenCalledWith(expect.stringContaining('/api/settings/data-snapshot/export')));
    expect(click).toHaveBeenCalled();
    expect(await screen.findByText(/Snapshot downloaded/)).toBeInTheDocument();
  });

  it('needs a file and an explicit policy before it can check, and cannot import before a clean check', async () => {
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);

    expect(screen.getByRole('button', { name: 'Check file' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: /Skip existing ids/ })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: /Replace existing ids/ })).not.toBeChecked();

    const input = container.querySelector('input[type="file"]');
    await user.upload(input as HTMLInputElement, new File(['{}'], 'snapshot.json', { type: 'application/json' }));
    expect(screen.getByRole('button', { name: 'Check file' })).toBeDisabled();

    await user.click(screen.getByRole('radio', { name: /Replace existing ids/ }));
    expect(screen.getByRole('button', { name: 'Check file' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
    expect(fetchWithRole).not.toHaveBeenCalled();
  });

  it('runs the dry run with the chosen policy and shows the counts', async () => {
    fetchWithRole.mockResolvedValue(ok(report({ policy: 'replace' })));
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);
    await chooseFileAndPolicy(user, container, /Replace existing ids/);

    await user.click(screen.getByRole('button', { name: 'Check file' }));

    await waitFor(() => expect(fetchWithRole).toHaveBeenCalledWith(
      expect.stringContaining('/api/settings/data-snapshot/import/dry-run?policy=replace'),
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByText(/Ready to import: 5 new rows/)).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'employees' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'actions' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeEnabled();
  });

  it('shows blocking conflicts and missing accounts and keeps the import disabled', async () => {
    fetchWithRole.mockResolvedValue(ok(report({
      importable: false,
      totals: undefined,
      blocking_conflict_count: 1,
      blocking_conflicts: [{ table: 'performance_plans', reason: "no account named 'planner' exists in this database" }],
      user_references: { matched: 0, cleared: {}, missing_accounts: ['planner'] },
    })));
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);
    await chooseFileAndPolicy(user, container);

    await user.click(screen.getByRole('button', { name: 'Check file' }));

    expect(await screen.findByText(/1 conflict\(s\) block this import/)).toBeInTheDocument();
    expect(screen.getByText(/no account named 'planner'/)).toBeInTheDocument();
    expect(screen.getByText(/not found here: planner/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
  });

  it('imports after confirmation and reports the counts', async () => {
    fetchWithRole
      .mockResolvedValueOnce(ok(report()))
      .mockResolvedValueOnce(ok(report({ dry_run: false, committed: true, totals: { incoming: 5, new: 4, existing_ids: 1, skipped: 1, replaced: 0 } })));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);
    await chooseFileAndPolicy(user, container);
    await user.click(screen.getByRole('button', { name: 'Check file' }));
    await screen.findByText(/Ready to import/);

    await user.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => expect(fetchWithRole).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/data-snapshot/import?policy=skip'),
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByText('Imported 4 new rows; 0 replaced, 1 skipped.')).toBeInTheDocument();
  });

  it('does not import when the confirmation is declined', async () => {
    fetchWithRole.mockResolvedValueOnce(ok(report()));
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);
    await chooseFileAndPolicy(user, container);
    await user.click(screen.getByRole('button', { name: 'Check file' }));
    await screen.findByText(/Ready to import/);

    await user.click(screen.getByRole('button', { name: 'Import' }));

    expect(fetchWithRole).toHaveBeenCalledTimes(1);
  });

  it('shows the server refusal when the check fails', async () => {
    fetchWithRole.mockResolvedValue({ ok: false, json: async () => ({ detail: 'Snapshot schema version 2 is not supported; this server reads version 1.' }) });
    const user = userEvent.setup();
    const { container } = render(<DataSnapshotPanel />);
    await chooseFileAndPolicy(user, container);

    await user.click(screen.getByRole('button', { name: 'Check file' }));

    expect(await screen.findByText(/schema version 2 is not supported/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
  });
});
