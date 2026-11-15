import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AiResponseCard from './AiResponseCard';
import type { AiChatResponsePayload, StructuredVisualCard } from '../../features/ai/types';
import { apiFetch } from '../../lib/apiClient';

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

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

  it('renders provenance badge, Copy summary button, and Different angle trigger for answer turns', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const onRegenerateAngle = vi.fn();
    const answerResp: AiChatResponsePayload = {
      ...responseWithBarCard(),
      outcome: 'answer',
      provider_used: 'cloudflare',
    };

    render(
      <MemoryRouter>
        <AiResponseCard
          response={answerResp}
          variationSeed={1}
          onRegenerateAngle={onRegenerateAngle}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('ai-provenance-badge')).toHaveTextContent('Verified PMS · Live Synthesis');

    fireEvent.click(screen.getByTestId('ai-regenerate-angle-btn'));
    expect(onRegenerateAngle).toHaveBeenCalledWith(2);

    fireEvent.click(screen.getByTestId('ai-copy-summary-btn'));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(
        'Dubai recorded 200 bookings; Ajman booking data is missing or unpublished.\n- Dubai recorded 200 bookings.',
      );
      expect(screen.getByTestId('ai-copy-summary-btn')).toHaveTextContent('Copied');
    });
  });

  it('toggles View details and Hide details cleanly in Brief mode', () => {
    const briefResp: AiChatResponsePayload = {
      ...responseWithBarCard(),
      answer_detail: 'brief',
      outcome: 'answer',
    };

    render(
      <MemoryRouter>
        <AiResponseCard response={briefResp} />
      </MemoryRouter>,
    );

    const viewBtn = screen.getByRole('button', { name: /View details/i });
    expect(viewBtn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(viewBtn);
    const hideBtn = screen.getByRole('button', { name: /Hide details/i });
    expect(hideBtn).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens failure tag selector on Not helpful and sends tagged feedback payload', async () => {
    mockedApiFetch.mockResolvedValueOnce({ success: true, trace_id: 'test-trace', rating: 'down' });

    render(
      <MemoryRouter>
        <AiResponseCard response={responseWithBarCard()} />
      </MemoryRouter>,
    );

    const notHelpfulBtn = screen.getByRole('button', { name: 'Flag response as inaccurate' });
    fireEvent.click(notHelpfulBtn);

    const panel = screen.getByTestId('ai-feedback-flag-panel');
    expect(panel).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Wrong data' }));
    fireEvent.change(screen.getByLabelText('Optional feedback note'), {
      target: { value: 'Ajman bookings were uploaded in sheet 2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send feedback' }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/feedback',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            trace_id: 'test-trace',
            rating: 'down',
            category: 'wrong_data',
            reason: 'Ajman bookings were uploaded in sheet 2',
          }),
        }),
      );
      expect(screen.getByText('Feedback saved')).toBeInTheDocument();
    });
  });
});
