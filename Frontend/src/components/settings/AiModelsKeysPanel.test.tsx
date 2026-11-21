import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AiModelsKeysPanel, type AiProviderConfigItem } from './AiModelsKeysPanel';
import { apiFetch } from '../../lib/apiClient';

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

function provider(overrides: Partial<AiProviderConfigItem> & Pick<AiProviderConfigItem, 'provider' | 'label'>): AiProviderConfigItem {
  return {
    enabled: true,
    enabled_source: 'db',
    primary_model: 'model-default',
    alternate_model: null,
    primary_model_source: 'db',
    account_id_masked: '',
    alternate_account_id_masked: '',
    account_id_source: 'none',
    alternate_account_id_source: 'none',
    primary_key: { slot: 'primary', configured: false, source: 'none', masked_preview: '' },
    alternate_key: { slot: 'alternate', configured: false, source: 'none', masked_preview: '' },
    active_key_slot: 'primary',
    auto_failover_key: true,
    daily_limit: null,
    updated_at: '2026-11-18T10:00:00Z',
    ...overrides,
  };
}

const CLOUDFLARE = provider({
  provider: 'cloudflare',
  label: 'Cloudflare Workers AI · Fallback chat',
  primary_model: '@cf/ibm-granite/granite-4.0-h-micro',
  alternate_model: '@cf/zai-org/glm-4.7-flash',
  account_id_masked: 'acct••••1234',
  account_id_source: 'db',
  primary_key: { slot: 'primary', configured: true, source: 'db', masked_preview: '••••7a2f' },
  alternate_key: { slot: 'alternate', configured: true, source: 'db', masked_preview: '••••3b9e' },
});

const NVIDIA = provider({
  provider: 'nvidia',
  label: 'NVIDIA NIM · Primary chat and feedback',
  primary_model: 'nvidia/nemotron-3.5-super-vl-120b-a12b',
  enabled: false,
  daily_limit: 50,
  primary_key: { slot: 'primary', configured: true, source: 'db', masked_preview: 'nvapi-••••7a2f' },
});

const PROVIDERS = [CLOUDFLARE, NVIDIA];

function listResponse() {
  return { success: true, providers: PROVIDERS };
}

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockResolvedValue(listResponse());
});

async function renderPanel() {
  render(<AiModelsKeysPanel />);
  await screen.findByTestId('provider-card-cloudflare');
}

describe('AI models & keys panel', () => {
  it('loads all providers and only shows masked key previews', async () => {
    await renderPanel();

    expect(screen.getByTestId('provider-card-cloudflare')).toBeInTheDocument();
    expect(screen.getByTestId('provider-card-nvidia')).toBeInTheDocument();
    expect(screen.queryByTestId('provider-card-gemini')).not.toBeInTheDocument();

    const cloudflare = screen.getByTestId('provider-card-cloudflare');
    expect(within(cloudflare).getByText('••••7a2f')).toBeInTheDocument();
    expect(within(cloudflare).getByText('••••3b9e')).toBeInTheDocument();
    expect(within(cloudflare).getByText(/acct••••1234/)).toBeInTheDocument();
    expect(mockedApiFetch).toHaveBeenCalledWith('/api/ai/admin/providers');
  });

  it('shows supported providers when an older backend still returns Gemini', async () => {
    mockedApiFetch.mockResolvedValueOnce({
      success: true,
      providers: [
        { ...NVIDIA, provider: 'gemini', label: 'Google Gemini' },
        ...PROVIDERS,
      ],
    });

    await renderPanel();

    expect(screen.getByTestId('provider-card-nvidia')).toBeInTheDocument();
    expect(screen.queryByTestId('provider-card-gemini')).not.toBeInTheDocument();
    expect(screen.getByText('2 of 2 providers configured')).toBeInTheDocument();
  });

  it('saves a replacement key without ever rendering it back', async () => {
    const updated = {
      ...CLOUDFLARE,
      primary_model: '@cf/meta/llama-3.1-8b-instruct',
      primary_key: { slot: 'primary' as const, configured: true, source: 'db' as const, masked_preview: '••••9999' },
    };
    mockedApiFetch.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/ai/admin/providers/cloudflare' && options?.method === 'PUT') {
        return { success: true, message: 'AI provider configuration saved', provider: updated };
      }
      return listResponse();
    });

    const user = userEvent.setup();
    await renderPanel();
    const card = screen.getByTestId('provider-card-cloudflare');

    await user.clear(within(card).getByLabelText('Primary model'));
    await user.type(within(card).getByLabelText('Primary model'), 'my-custom-model');
    await user.type(within(card).getByLabelText('Primary API key'), 'brand-new-secret-key');
    await user.click(within(card).getByRole('button', { name: 'Save Cloudflare settings' }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/admin/providers/cloudflare',
        expect.objectContaining({ method: 'PUT' }),
      );
    });
    const putCall = mockedApiFetch.mock.calls.find(
      ([url, options]) => url === '/api/ai/admin/providers/cloudflare' && options?.method === 'PUT',
    );
    const payload = JSON.parse(String(putCall?.[1]?.body));
    expect(payload.primary_model).toBe('my-custom-model');
    expect(payload.primary_api_key).toBe('brand-new-secret-key');
    expect(screen.queryByDisplayValue('brand-new-secret-key')).not.toBeInTheDocument();
    expect(await screen.findByText('AI provider configuration saved')).toBeInTheDocument();
  });

  it('switches the active key with one click', async () => {
    const switched = { ...CLOUDFLARE, active_key_slot: 'alternate' as const };
    mockedApiFetch.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/ai/admin/providers/cloudflare/switch-key' && options?.method === 'POST') {
        return { success: true, message: 'Active key switched to alternate', provider: switched };
      }
      return listResponse();
    });

    const user = userEvent.setup();
    await renderPanel();
    const card = screen.getByTestId('provider-card-cloudflare');
    await user.click(within(card).getByRole('button', { name: 'Use Alternate key' }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/admin/providers/cloudflare/switch-key',
        expect.objectContaining({ method: 'POST' }),
      );
    });
    const call = mockedApiFetch.mock.calls.find(([url]) =>
      String(url).endsWith('/switch-key'),
    );
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ slot: 'alternate' });
    expect(await screen.findByText('Active key switched to alternate')).toBeInTheDocument();
    expect(within(card).getByText('Active: Alternate')).toBeInTheDocument();
  });

  it('shows live test latency and status without exposing the key', async () => {
    mockedApiFetch.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/ai/admin/providers/cloudflare/test' && options?.method === 'POST') {
        return {
          success: true,
          data: {
            ok: true,
            latency_ms: 42.4,
            status_code: 200,
            message: 'Cloudflare token verified',
            tested_model: '@cf/ibm-granite/granite-4.0-h-micro',
            tested_slot: 'primary',
          },
        };
      }
      return listResponse();
    });

    const user = userEvent.setup();
    await renderPanel();
    const card = screen.getByTestId('provider-card-cloudflare');
    await user.click(within(card).getByRole('button', { name: 'Test Primary key' }));

    expect(await within(card).findByText('Verified · HTTP 200 · 42 ms · Cloudflare token verified')).toBeInTheDocument();
    const call = mockedApiFetch.mock.calls.find(([url]) =>
      String(url).endsWith('/test'),
    );
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ slot: 'primary' });
    expect(JSON.stringify(call?.[1])).not.toContain('••••7a2f');
  });

  it('requires inline confirmation before clearing a stored key', async () => {
    const cleared = {
      ...CLOUDFLARE,
      primary_key: { slot: 'primary' as const, configured: false, source: 'none' as const, masked_preview: '' },
    };
    mockedApiFetch.mockImplementation(async (url: string, options?: RequestInit) => {
      if (url === '/api/ai/admin/providers/cloudflare' && options?.method === 'PUT') {
        return { success: true, message: 'AI provider configuration saved', provider: cleared };
      }
      return listResponse();
    });

    const user = userEvent.setup();
    await renderPanel();
    const card = screen.getByTestId('provider-card-cloudflare');

    await user.click(within(card).getByRole('button', { name: 'Clear saved Primary key' }));
    expect(within(card).getByText('Clear this key?')).toBeInTheDocument();
    expect(
      mockedApiFetch.mock.calls.some(([, options]) => options?.method === 'PUT'),
    ).toBe(false);

    await user.click(within(card).getByRole('button', { name: 'Confirm' }));
    await waitFor(() => {
      const putCall = mockedApiFetch.mock.calls.find(
        ([url, options]) => url === '/api/ai/admin/providers/cloudflare' && options?.method === 'PUT',
      );
      expect(JSON.parse(String(putCall?.[1]?.body))).toEqual({
        clear_primary_api_key: true,
      });
    });
  });

  it('surfaces a load failure with a retry action', async () => {
    mockedApiFetch.mockRejectedValueOnce(new Error('Admin access required'));
    render(<AiModelsKeysPanel />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load AI model settings');
    expect(screen.getByRole('alert')).toHaveTextContent('Admin access required');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
