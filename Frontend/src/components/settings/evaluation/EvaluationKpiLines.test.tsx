import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EvaluationLine } from '../evaluationSettings';
import { EvaluationKpiLines, type EvaluationKpiLinesProps } from './EvaluationKpiLines';

const FIXTURE: EvaluationLine[] = [
  { kpi_key: 'AHT', label: 'AHT', weight: 0.5, direction: 'lower_better', target: 2.5, target_mode: 'fixed', unit: 'hours' },
  { kpi_key: 'QualityErrors', label: 'Quality errors', weight: 0.4, direction: 'higher_better', target: 0.55, target_mode: 'workbook', unit: '%' },
  { kpi_key: 'Calls', label: 'Calls', weight: 0, direction: 'higher_better', target: 65, target_mode: 'fixed', unit: 'count' },
  { kpi_key: 'Mystery', label: 'Mystery', weight: 0.1, direction: 'custom_index', target: 65, target_mode: 'fixed' },
  { kpi_key: 'Quality', label: 'Quality', weight: 0.1, direction: 'higher_better', target: null, target_mode: 'workbook', unit: '%' },
  { kpi_key: 'HandleTime', label: 'Handle time', weight: 0.1, direction: 'higher_better', target: 1, target_mode: 'fixed', unit: 'minutes' },
];

function props(overrides: Partial<EvaluationKpiLinesProps> = {}): EvaluationKpiLinesProps {
  return {
    lines: FIXTURE,
    referenceLines: FIXTURE,
    textDrafts: {},
    draftProblems: [],
    totalWeight: 0.9,
    inputBlocked: false,
    weightTotalInvalid: false,
    periodLoading: false,
    blocked: false,
    busy: false,
    approved: false,
    directionOwned: false,
    onEditText: vi.fn(),
    onUpdateLine: vi.fn(),
    ...overrides,
  };
}

function group(name: string) {
  return screen.getByRole('group', { name });
}

describe('EvaluationKpiLines grid', () => {
  it('renders one named group per KPI, under an Indicators heading', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(screen.getByRole('heading', { name: 'Indicators' })).toBeInTheDocument();
    for (const name of ['AHT', 'Quality errors', 'Calls', 'Mystery', 'Quality', 'Handle time']) {
      expect(group(name)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('group')).toHaveLength(6);
  });

  it('keeps every control reachable by its existing aria-label', () => {
    render(<EvaluationKpiLines {...props()} />);
    for (const kpi of ['AHT', 'QualityErrors', 'Calls', 'Mystery', 'Quality', 'HandleTime']) {
      expect(screen.getByLabelText(`${kpi} target`)).toBeInTheDocument();
      expect(screen.getByLabelText(`${kpi} weight`)).toBeInTheDocument();
      expect(screen.getByLabelText(`${kpi} direction`)).toBeInTheDocument();
      expect(screen.getByLabelText(`${kpi} source`)).toBeInTheDocument();
    }
  });

  it('shows each instruction once, above the grid, and not in every row', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(screen.getAllByText(/Enter a percentage\. 65 is stored as 0\.65\./)).toHaveLength(1);
    expect(screen.getAllByText(/No unit was provided\./)).toHaveLength(1);
    expect(screen.getAllByText(/Enter a percentage of this scorecard\. 60 is stored as 0\.6\./)).toHaveLength(1);
  });

  it('describes each target input through the shared instruction and its own saved value', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(screen.getByLabelText('AHT target')).toHaveAccessibleDescription(/Enter hours\. The value is stored as entered\..*Saved target: 2\.5 hours\./);
    expect(screen.getByLabelText('QualityErrors weight')).toHaveAccessibleDescription(/Zero remains a diagnostic weight\..*Saved weight: 40%\./);
  });

  it('places a problem message inside the row it belongs to and marks its input invalid', () => {
    render(<EvaluationKpiLines {...props({
      draftProblems: [{ kpiKey: 'AHT', field: 'target', message: 'This entry is blank. Saved target remains 2.5 hours.' }],
    })} />);
    expect(within(group('AHT')).getByText(/This entry is blank/)).toBeInTheDocument();
    expect(screen.getByLabelText('AHT target')).toHaveAttribute('aria-invalid', 'true');
    expect(within(group('Calls')).queryByText(/This entry is blank/)).not.toBeInTheDocument();
  });
});

describe('EvaluationKpiLines disabled state', () => {
  it('disables the target, weight, direction, source and track controls while a request is busy', () => {
    render(<EvaluationKpiLines {...props({ busy: true })} />);
    expect(screen.getByLabelText('AHT target')).toBeDisabled();
    expect(screen.getByLabelText('AHT weight')).toBeDisabled();
    expect(screen.getByLabelText('AHT direction')).toBeDisabled();
    expect(screen.getByLabelText('AHT source')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Track AHT only' })).toBeDisabled();
  });

  it('disables the same controls on an approved month', () => {
    render(<EvaluationKpiLines {...props({ approved: true })} />);
    expect(screen.getByLabelText('QualityErrors target')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Track AHT only' })).toBeDisabled();
  });

  it('disables an unsupported row, keeps its read-only controls read-only, and keeps the formula note', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(screen.getByLabelText('Mystery target')).toBeDisabled();
    const direction = screen.getByLabelText('Mystery direction');
    expect(direction).toBeDisabled();
    expect(direction).toHaveAttribute('readonly');
    expect(within(group('Mystery')).getByText(/This formula is blocked in this release/)).toBeInTheDocument();
  });

  it('leaves supported rows enabled when nothing is busy or approved', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(screen.getByLabelText('AHT target')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Track AHT only' })).toBeEnabled();
  });
});

describe('EvaluationKpiLines row states', () => {
  it('shows Tracking only with the hint, and no track button, for a zero-weight row', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(within(group('Calls')).getByText('Tracking only')).toBeInTheDocument();
    expect(within(group('Calls')).getByText('Enter a weight above 0% to include in the score.')).toBeInTheDocument();
    expect(within(group('Calls')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows Included in score and the track button for a weighted row', () => {
    render(<EvaluationKpiLines {...props()} />);
    expect(within(group('AHT')).getByText('Included in score')).toBeInTheDocument();
    expect(within(group('AHT')).getByRole('button', { name: 'Track AHT only' })).toBeInTheDocument();
  });

  it('marks a row as Edited only when its draft differs from the saved line', () => {
    render(<EvaluationKpiLines {...props({ textDrafts: { QualityErrors: { targetText: '60' } } })} />);
    expect(within(group('Quality errors')).getByText('Edited')).toBeInTheDocument();
    expect(group('Quality errors')).toHaveAttribute('data-edited', 'true');
    expect(within(group('AHT')).queryByText('Edited')).not.toBeInTheDocument();
  });

  it('does not mark a row Edited when the draft text is the saved value', () => {
    render(<EvaluationKpiLines {...props({ textDrafts: { QualityErrors: { targetText: '55' } } })} />);
    expect(within(group('Quality errors')).queryByText('Edited')).not.toBeInTheDocument();
  });
});

describe('EvaluationKpiLines summary, loading and empty states', () => {
  it('shows a valid total-weight summary with an icon-and-text cue', () => {
    render(<EvaluationKpiLines {...props({ totalWeight: 1 })} />);
    expect(screen.getByText('Total weight: 100%')).toBeInTheDocument();
    expect(screen.getByText('Valid')).toBeInTheDocument();
    expect(screen.getByText('Weights are ready to save. Tracking-only indicators do not contribute to the score.')).toBeInTheDocument();
  });

  it('shows the needs-attention cue and sentence when the total is invalid', () => {
    render(<EvaluationKpiLines {...props({ weightTotalInvalid: true })} />);
    expect(screen.getByText('Needs attention')).toBeInTheDocument();
    expect(screen.getByText('Set the scored indicators to a total of 100% before saving. Other weights are not changed automatically.')).toBeInTheDocument();
  });

  it('keeps the loading text and shows no rows while the month loads', () => {
    render(<EvaluationKpiLines {...props({ periodLoading: true })} />);
    expect(screen.getByText('Loading this month…')).toBeInTheDocument();
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('shows a short message when the month has no indicators', () => {
    render(<EvaluationKpiLines {...props({ lines: [], referenceLines: [], totalWeight: 0 })} />);
    expect(screen.getByText('This month has no indicators to edit.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Indicators' })).toBeInTheDocument();
  });

  it('renders nothing for a blocked scope that is not loading', () => {
    render(<EvaluationKpiLines {...props({ blocked: true })} />);
    expect(screen.queryByRole('heading', { name: 'Indicators' })).not.toBeInTheDocument();
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('forwards edits to the existing handlers unchanged', () => {
    const onEditText = vi.fn();
    render(<EvaluationKpiLines {...props({ onEditText })} />);
    fireEvent.change(screen.getByLabelText('AHT target'), { target: { value: '3' } });
    expect(onEditText).toHaveBeenCalledWith('AHT', 'targetText', '3');
    fireEvent.click(screen.getByRole('button', { name: 'Track AHT only' }));
    expect(onEditText).toHaveBeenCalledWith('AHT', 'weightText', '0');
  });
});
