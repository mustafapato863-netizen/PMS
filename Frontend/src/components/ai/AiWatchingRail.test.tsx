import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AiWatchingRail from './AiWatchingRail';
import type { AiWatchingAlertItem } from '../../features/ai/types';

const pharmacyAlert: AiWatchingAlertItem = {
  id: 'watch-pharmacy',
  title: 'Pharmacy score dropped',
  subtitle: 'Waiting time widened',
  severity: 'warning',
  badge_text: 'Pharmacy',
  prompt_to_ask: 'Diagnose why Pharmacy triggered the drop',
};

describe('AiWatchingRail alert badge', () => {
  it('names the watching count without a Call Center label and shows the scope badge it was given', () => {
    render(
      <AiWatchingRail
        alerts={[pharmacyAlert]}
        guardrails={[]}
        isLoading={false}
        onSelectAlert={() => undefined}
      />,
    );

    expect(screen.getByLabelText('1 watching alert')).toHaveTextContent('1');
    expect(screen.getByText('Pharmacy')).toBeInTheDocument();
    expect(screen.queryByText(/Call Center/i)).not.toBeInTheDocument();
  });
});
