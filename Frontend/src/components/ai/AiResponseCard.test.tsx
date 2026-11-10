import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AiResponseCard from './AiResponseCard';
import type { AiChatResponsePayload, StructuredVisualCard } from '../../features/ai/types';

function responseWithBarCard(): AiChatResponsePayload {
  const card: StructuredVisualCard = {
    card_type: 'horizontal_bar',
    title: 'UAE Branch Booking Counts · Inbound',
    subtitle: 'Booking counts per branch',
    bars: [
      {
        label: 'Inbound · Dubai',
        value: 200,
        display_value: '200 bookings',
        target_value: null,
        secondary_label: null,
        severity: 'neutral',
      },
      {
        label: 'Inbound · Ajman',
        value: null,
        display_value: 'Unavailable',
        target_value: null,
        secondary_label: 'Bookings unrecorded',
        severity: 'neutral',
      },
    ],
    items: [],
    kpi_rows: [],
  };
  return {
    trace_id: 'test-trace',
    headline: 'Dubai recorded 200 bookings; Ajman booking data is missing or unpublished.',
    narrative_bullets: ['Dubai recorded 200 bookings.'],
    visual_cards: [card],
    citations: [],
    deep_links: [],
    suggested_followups: [],
    resolved_session_state: {},
    domain_guardrail_notes: [],
    tool_calls: [],
    provider_used: 'deterministic',
    model_used: 'rules',
    latency_ms: 1,
  } as AiChatResponsePayload;
}

describe('AiResponseCard — unrecorded bars (Item 3d)', () => {
  it('renders no bar fill for a null-value bar and keeps the Unavailable badge', () => {
    const { container } = render(
      <MemoryRouter>
        <AiResponseCard response={responseWithBarCard()} />
      </MemoryRouter>,
    );
    // The recorded bar shows its count; the unrecorded bar shows Unavailable.
    expect(screen.getByText('200 bookings')).toBeTruthy();
    expect(screen.getByText('Unavailable')).toBeTruthy();
    // The bar fills are the gradient divs inside the track: the recorded
    // bar has a non-zero width, the unrecorded bar has width 0% (no stub).
    const fills = [...container.querySelectorAll('div[style*="width:"]')].map(
      (el) => (el as HTMLElement).style.width,
    );
    expect(fills).toContain('0%');
    expect(fills.some((w) => w !== '0%')).toBe(true);
  });
});
