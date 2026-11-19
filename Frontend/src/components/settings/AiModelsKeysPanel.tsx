import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Cloud,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import { apiFetch } from '../../lib/apiClient';

export type AiProviderName = 'cloudflare' | 'gemini' | 'nvidia';
export type AiKeySlot = 'primary' | 'alternate';
export type AiKeySource = 'db' | 'env' | 'none';

export interface AiProviderKeyState {
  slot: AiKeySlot;
  configured: boolean;
  source: AiKeySource;
  masked_preview: string;
}

export interface AiProviderConfigItem {
  provider: AiProviderName;
  label: string;
  enabled: boolean;
  enabled_source: string;
  primary_model: string;
  alternate_model: string | null;
  primary_model_source: string;
  account_id_masked: string;
  alternate_account_id_masked: string;
  account_id_source: string;
  alternate_account_id_source: string;
  primary_key: AiProviderKeyState;
  alternate_key: AiProviderKeyState;
  active_key_slot: AiKeySlot;
  auto_failover_key: boolean;
  daily_limit: number | null;
  updated_at: string | null;
}

interface AiProviderConfigListResponse {
  success: boolean;
  providers: AiProviderConfigItem[];
}

interface AiProviderConfigResponse {
  success: boolean;
  message?: string;
  provider: AiProviderConfigItem;
}

interface AiProviderSwitchKeyResponse {
  success: boolean;
  message?: string;
  provider: AiProviderConfigItem;
}

interface AiProviderTestResponse {
  success: boolean;
  message?: string;
  data: {
    ok: boolean;
    latency_ms: number;
    status_code: number;
    message: string;
    tested_model: string;
    tested_slot: AiKeySlot;
  };
}

interface ProviderDraft {
  enabled: boolean;
  primaryModel: string;
  alternateModel: string;
  accountId: string;
  alternateAccountId: string;
  primaryKey: string;
  alternateKey: string;
  autoFailoverKey: boolean;
  dailyLimit: string;
}

type KeyConfirmState = Record<string, boolean>;
type TestState = Record<string, { state: 'loading' } | { state: 'done'; result: AiProviderTestResponse['data'] } | { state: 'error'; message: string }>;

const PROVIDER_ICONS: Record<AiProviderName, typeof Cloud> = {
  cloudflare: Cloud,
  gemini: Sparkles,
  nvidia: ShieldCheck,
};

const PROVIDER_ROLE: Record<AiProviderName, string> = {
  cloudflare: 'Primary chat provider',
  gemini: 'Fallback chat provider',
  nvidia: 'Feedback root-cause analyzer',
};

const MODEL_PRESETS: Record<AiProviderName, string[]> = {
  cloudflare: [
    '@cf/ibm-granite/granite-4.0-h-micro',
    '@cf/zai-org/glm-4.7-flash',
    '@cf/meta/llama-3.1-8b-instruct',
  ],
  gemini: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash-lite'],
  nvidia: [
    'nvidia/nemotron-3.5-super-vl-120b-a12b',
    'nvidia/llama-3.3-nemotron-super-49b-v1.5',
  ],
};

const SOURCE_LABEL: Record<AiKeySource, string> = {
  db: 'Stored',
  env: 'Environment',
  none: 'Not configured',
};

function draftFromProvider(item: AiProviderConfigItem): ProviderDraft {
  return {
    enabled: item.enabled,
    primaryModel: item.primary_model,
    alternateModel: item.alternate_model ?? '',
    accountId: '',
    alternateAccountId: '',
    primaryKey: '',
    alternateKey: '',
    autoFailoverKey: item.auto_failover_key,
    dailyLimit: item.daily_limit === null ? '' : String(item.daily_limit),
  };
}

function keyId(provider: AiProviderName, slot: AiKeySlot): string {
  return `${provider}:${slot}`;
}

function slotLabel(slot: AiKeySlot): string {
  return slot === 'primary' ? 'Primary' : 'Alternate';
}

function sourceLabel(source: string): string {
  return SOURCE_LABEL[source as AiKeySource] ?? SOURCE_LABEL.none;
}

function sourceBadgeClass(source: AiKeySource): string {
  if (source === 'db') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (source === 'env') return 'bg-sky-50 text-sky-700 border-sky-200';
  return 'bg-slate-100 text-slate-500 border-slate-200';
}

/**
 * Admin-only manager for AI provider models and encrypted API keys.
 *
 * Credentials are write-only in this UI: the server returns masked previews,
 * never plaintext, and a blank key input leaves the stored value untouched.
 */
export function AiModelsKeysPanel() {
  const [providers, setProviders] = useState<AiProviderConfigItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const [savingProvider, setSavingProvider] = useState<AiProviderName | null>(null);
  const [switchingProvider, setSwitchingProvider] = useState<AiProviderName | null>(null);
  const [confirmClear, setConfirmClear] = useState<KeyConfirmState>({});
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [tests, setTests] = useState<TestState>({});

  const applyProviders = useCallback((items: AiProviderConfigItem[]) => {
    setProviders(items);
    setDrafts(
      Object.fromEntries(items.map((item) => [item.provider, draftFromProvider(item)])),
    );
  }, []);

  const loadProviders = useCallback(async (signal?: { cancelled: boolean }) => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const response = await apiFetch<AiProviderConfigListResponse>('/api/ai/admin/providers');
      if (signal?.cancelled) return;
      const items = Array.isArray(response?.providers) ? response.providers : [];
      applyProviders(items);
    } catch (error) {
      if (signal?.cancelled) return;
      const message = error instanceof Error ? error.message : 'Unable to load AI provider settings.';
      setLoadError(message);
    } finally {
      if (!signal?.cancelled) setIsLoading(false);
    }
  }, [applyProviders]);

  useEffect(() => {
    const signal = { cancelled: false };
    const timer = setTimeout(() => {
      void loadProviders(signal);
    }, 0);
    return () => {
      signal.cancelled = true;
      clearTimeout(timer);
    };
  }, [loadProviders]);

  const updateDraft = useCallback(
    (provider: AiProviderName, changes: Partial<ProviderDraft>) => {
      setDrafts((previous) => ({
        ...previous,
        [provider]: { ...previous[provider], ...changes },
      }));
    },
    [],
  );

  const showBanner = (kind: 'success' | 'error', text: string) => {
    setBanner({ kind, text });
  };

  const replaceProvider = (
    updated: AiProviderConfigItem,
    options: { resetDraft?: boolean } = {},
  ) => {
    setProviders((previous) =>
      previous.map((item) => (item.provider === updated.provider ? updated : item)),
    );
    setDrafts((previous) => {
      const draft = previous[updated.provider];
      if (!draft || options.resetDraft) {
        return { ...previous, [updated.provider]: draftFromProvider(updated) };
      }
      return {
        ...previous,
        [updated.provider]: {
          ...draft,
          enabled: updated.enabled,
          autoFailoverKey: updated.auto_failover_key,
          dailyLimit: updated.daily_limit === null ? '' : String(updated.daily_limit),
        },
      };
    });
  };

  const handleSave = async (provider: AiProviderName) => {
    const draft = drafts[provider];
    if (!draft) return;
    setSavingProvider(provider);
    setBanner(null);
    try {
      const payload: Record<string, unknown> = {
        enabled: draft.enabled,
        primary_model: draft.primaryModel.trim(),
        auto_failover_key: draft.autoFailoverKey,
      };
      if (provider === 'cloudflare') {
        payload.alternate_model = draft.alternateModel.trim();
        if (draft.accountId.trim()) payload.account_id = draft.accountId.trim();
        if (draft.alternateAccountId.trim()) {
          payload.alternate_account_id = draft.alternateAccountId.trim();
        }
      }
      if (provider === 'nvidia' && draft.dailyLimit.trim() !== '') {
        const parsedLimit = Number(draft.dailyLimit);
        if (Number.isFinite(parsedLimit)) {
          payload.daily_limit = Math.max(1, Math.min(500, Math.trunc(parsedLimit)));
        }
      }
      if (draft.primaryKey.trim()) payload.primary_api_key = draft.primaryKey.trim();
      if (draft.alternateKey.trim()) payload.alternate_api_key = draft.alternateKey.trim();

      const response = await apiFetch<AiProviderConfigResponse>(
        `/api/ai/admin/providers/${provider}`,
        { method: 'PUT', body: JSON.stringify(payload) },
      );
      replaceProvider(response.provider, { resetDraft: true });
      showBanner('success', response.message || 'AI provider configuration saved.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to save AI provider settings.';
      showBanner('error', message);
    } finally {
      setSavingProvider(null);
    }
  };

  const handleClear = async (provider: AiProviderName, slot: AiKeySlot) => {
    const draft = drafts[provider];
    if (!draft) return;
    setSavingProvider(provider);
    setBanner(null);
    try {
      const payload: Record<string, unknown> =
        slot === 'primary'
          ? { clear_primary_api_key: true }
          : { clear_alternate_api_key: true };
      const response = await apiFetch<AiProviderConfigResponse>(
        `/api/ai/admin/providers/${provider}`,
        { method: 'PUT', body: JSON.stringify(payload) },
      );
      replaceProvider(response.provider);
      updateDraft(
        provider,
        slot === 'primary' ? { primaryKey: '' } : { alternateKey: '' },
      );
      setConfirmClear((previous) => ({ ...previous, [keyId(provider, slot)]: false }));
      showBanner(
        'success',
        `${slotLabel(slot)} key cleared. ${
          response.provider[slot === 'primary' ? 'primary_key' : 'alternate_key'].source === 'env'
            ? 'The environment default is now in use.'
            : 'No key is configured for that slot.'
        }`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to clear the stored key.';
      showBanner('error', message);
    } finally {
      setSavingProvider(null);
    }
  };

  const handleSwitch = async (provider: AiProviderName) => {
    const item = providers.find((candidate) => candidate.provider === provider);
    if (!item) return;
    const target: AiKeySlot = item.active_key_slot === 'primary' ? 'alternate' : 'primary';
    setSwitchingProvider(provider);
    setBanner(null);
    try {
      const response = await apiFetch<AiProviderSwitchKeyResponse>(
        `/api/ai/admin/providers/${provider}/switch-key`,
        { method: 'POST', body: JSON.stringify({ slot: target }) },
      );
      replaceProvider(response.provider);
      showBanner('success', response.message || `Active key switched to ${target}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to switch the active key.';
      showBanner('error', message);
    } finally {
      setSwitchingProvider(null);
    }
  };

  const handleTest = async (provider: AiProviderName, slot: AiKeySlot) => {
    const item = providers.find((candidate) => candidate.provider === provider);
    const draft = drafts[provider];
    if (!item || !draft) return;
    const id = keyId(provider, slot);
    setTests((previous) => ({ ...previous, [id]: { state: 'loading' } }));
    try {
      const payload: Record<string, unknown> = { slot };
      const enteredKey = slot === 'primary' ? draft.primaryKey.trim() : draft.alternateKey.trim();
      if (enteredKey) payload.api_key = enteredKey;
      if (draft.primaryModel.trim()) payload.model = draft.primaryModel.trim();
      if (provider === 'cloudflare') {
        const accountId =
          slot === 'alternate' ? draft.alternateAccountId.trim() : draft.accountId.trim();
        if (accountId) payload.account_id = accountId;
      }
      const response = await apiFetch<AiProviderTestResponse>(
        `/api/ai/admin/providers/${provider}/test`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
      setTests((previous) => ({ ...previous, [id]: { state: 'done', result: response.data } }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'The live key test could not run.';
      setTests((previous) => ({ ...previous, [id]: { state: 'error', message } }));
    }
  };

  const configuredCount = useMemo(
    () => providers.filter((item) => item.primary_key.configured || item.alternate_key.configured).length,
    [providers],
  );

  if (isLoading) {
    return (
      <div className="space-y-4" aria-label="Loading AI provider settings">
        <div className="h-28 animate-pulse rounded-2xl bg-slate-100" />
        <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
        <div className="h-64 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800">
        <p className="font-bold">Unable to load AI model settings</p>
        <p className="mt-1 text-xs">{loadError}</p>
        <button
          type="button"
          onClick={() => void loadProviders()}
          className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-white px-3 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-100"
        >
          <RefreshCw size={12} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <KeyRound size={20} />
          </div>
          <div>
            <h2 className="text-base font-extrabold text-slate-900">AI Models &amp; Keys</h2>
            <p className="mt-0.5 max-w-2xl text-xs font-medium text-slate-500">
              Manage the primary chat, fallback chat, and feedback analyzer providers. Keys are encrypted
              at rest, sent only to their provider, and never displayed again after saving.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadProviders()}
          className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-bold text-slate-700 hover:border-indigo-400 hover:text-indigo-600"
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-xs font-semibold text-emerald-900">
        <ShieldCheck size={15} className="shrink-0" />
        <span>
          Secrets are stored with Fernet encryption and masked on every read. Audit entries record which
          fields changed, never the key material.
        </span>
        <span className="ml-auto rounded-full border border-emerald-200 bg-white px-2.5 py-0.5 tabular-nums text-emerald-700">
          {configuredCount} of {providers.length} providers configured
        </span>
      </div>

      {banner && (
        <div
          role={banner.kind === 'error' ? 'alert' : 'status'}
          className={`flex items-center justify-between gap-2 rounded-xl border px-4 py-2.5 text-xs font-semibold ${
            banner.kind === 'error'
              ? 'border-rose-200 bg-rose-50 text-rose-800'
              : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}
        >
          <span>{banner.text}</span>
          <button
            type="button"
            aria-label="Dismiss notification"
            onClick={() => setBanner(null)}
            className="rounded p-0.5 hover:bg-black/5"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {providers.map((item) => {
        const draft = drafts[item.provider] ?? draftFromProvider(item);
        const Icon = PROVIDER_ICONS[item.provider];
        const saving = savingProvider === item.provider;
        const switching = switchingProvider === item.provider;
        const activeSlot = item.active_key_slot;
        const standbySlot: AiKeySlot = activeSlot === 'primary' ? 'alternate' : 'primary';
        const standbyState = standbySlot === 'primary' ? item.primary_key : item.alternate_key;

        return (
          <section
            key={item.provider}
            data-testid={`provider-card-${item.provider}`}
            className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-xs"
            aria-label={`${item.label} settings`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                  <Icon size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">{item.label}</h3>
                  <p className="text-xs font-medium text-slate-500">{PROVIDER_ROLE[item.provider]}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-bold text-slate-600">
                  Active: {slotLabel(activeSlot)}
                </span>
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-slate-200 px-2.5 py-1 text-xs font-bold text-slate-700">
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={`${item.label} enabled`}
                    checked={draft.enabled}
                    onChange={(event) => updateDraft(item.provider, { enabled: event.target.checked })}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                  />
                  Enabled
                </label>
              </div>
            </div>

            <div className="space-y-5 px-5 py-4">
              <div className="space-y-2">
                <label
                  htmlFor={`${item.provider}-primary-model`}
                  className="block text-xs font-bold text-slate-700"
                >
                  {item.provider === 'nvidia' ? 'Analyzer model' : 'Primary model'}
                </label>
                <input
                  id={`${item.provider}-primary-model`}
                  value={draft.primaryModel}
                  onChange={(event) => updateDraft(item.provider, { primaryModel: event.target.value })}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                />
                <div className="flex flex-wrap gap-1.5">
                  {MODEL_PRESETS[item.provider].map((model) => (
                    <button
                      key={model}
                      type="button"
                      onClick={() => updateDraft(item.provider, { primaryModel: model })}
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                        draft.primaryModel === model
                          ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                          : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-300 hover:text-indigo-700'
                      }`}
                    >
                      {model}
                    </button>
                  ))}
                </div>
                {item.primary_model_source === 'db' && (
                  <p className="text-xs font-medium text-slate-500">
                    Overrides the environment default. Clear the field and save to fall back.
                  </p>
                )}
              </div>

              {item.provider === 'cloudflare' && (
                <div className="space-y-2">
                  <label
                    htmlFor="cloudflare-alternate-model"
                    className="block text-xs font-bold text-slate-700"
                  >
                    Alternate model
                  </label>
                  <input
                    id="cloudflare-alternate-model"
                    value={draft.alternateModel}
                    onChange={(event) =>
                      updateDraft(item.provider, { alternateModel: event.target.value })
                    }
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                  <p className="text-xs font-medium text-slate-500">
                    Used when a request explicitly asks for the alternate model.
                  </p>
                </div>
              )}

              {item.provider === 'cloudflare' && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {(
                    [
                      ['accountId', 'Account ID', item.account_id_masked, item.account_id_source],
                      [
                        'alternateAccountId',
                        'Alternate Account ID',
                        item.alternate_account_id_masked,
                        item.alternate_account_id_source,
                      ],
                    ] as const
                  ).map(([field, label, masked, source]) => (
                    <div key={field} className="space-y-1.5">
                      <label
                        htmlFor={`cloudflare-${field}`}
                        className="block text-xs font-bold text-slate-700"
                      >
                        {label}
                      </label>
                      <input
                        id={`cloudflare-${field}`}
                        type="password"
                        autoComplete="off"
                        value={draft[field]}
                        placeholder={masked || 'Paste the Cloudflare Account ID'}
                        onChange={(event) => updateDraft(item.provider, { [field]: event.target.value })}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                      />
                      <p className="text-xs font-medium text-slate-500">
                        {masked ? `Saved: ${masked}` : 'Not configured'}{' '}
                        <span className={`ml-1 rounded-full border px-1.5 py-0.5 ${sourceBadgeClass(source as AiKeySource)}`}>
                          {sourceLabel(source)}
                        </span>
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {item.provider === 'nvidia' && (
                <div className="space-y-1.5 sm:max-w-xs">
                  <label
                    htmlFor="nvidia-daily-limit"
                    className="block text-xs font-bold text-slate-700"
                  >
                    Daily analyzer limit
                  </label>
                  <input
                    id="nvidia-daily-limit"
                    type="number"
                    min={1}
                    max={500}
                    value={draft.dailyLimit}
                    onChange={(event) => updateDraft(item.provider, { dailyLimit: event.target.value })}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                  <p className="text-xs font-medium text-slate-500">
                    Requests allowed per day (1–500). Leave unchanged to keep the current limit.
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <p className="text-xs font-bold text-slate-700">API keys</p>
                <div className="grid gap-3 lg:grid-cols-2">
                  {(['primary', 'alternate'] as const).map((slot) => {
                    const keyState = slot === 'primary' ? item.primary_key : item.alternate_key;
                    const id = keyId(item.provider, slot);
                    const value = slot === 'primary' ? draft.primaryKey : draft.alternateKey;
                    const isVisible = visibleKeys[id] === true;
                    const awaitingConfirm = confirmClear[id] === true;
                    const test = tests[id];
                    return (
                      <div
                        key={slot}
                        className={`rounded-xl border p-3 ${
                          activeSlot === slot
                            ? 'border-indigo-200 bg-indigo-50/40'
                            : 'border-slate-200 bg-slate-50/40'
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-extrabold text-slate-900">
                              {slotLabel(slot)} key
                            </span>
                            {activeSlot === slot && (
                              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-bold text-indigo-700">
                                Active
                              </span>
                            )}
                            <span
                              className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${sourceBadgeClass(keyState.source)}`}
                            >
                              {sourceLabel(keyState.source)}
                            </span>
                          </div>
                          <span className="font-mono text-xs text-slate-500">
                            {keyState.masked_preview || 'Not configured'}
                          </span>
                        </div>

                        <div className="mt-2 flex items-center gap-1.5">
                          <input
                            id={`${item.provider}-${slot}-key`}
                            type={isVisible ? 'text' : 'password'}
                            autoComplete="new-password"
                            aria-label={`${slotLabel(slot)} API key`}
                            value={value}
                            placeholder={
                              keyState.configured
                                ? 'Enter a new key to replace the saved value'
                                : 'Paste the API key'
                            }
                            onChange={(event) =>
                              updateDraft(item.provider, {
                                [slot === 'primary' ? 'primaryKey' : 'alternateKey']:
                                  event.target.value,
                              })
                            }
                            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                          />
                          <button
                            type="button"
                            aria-label={`${isVisible ? 'Hide' : 'Show'} ${slotLabel(slot)} key input`}
                            onClick={() =>
                              setVisibleKeys((previous) => ({ ...previous, [id]: !isVisible }))
                            }
                            className="rounded-lg border border-slate-200 bg-white p-2 text-slate-500 hover:text-slate-800"
                          >
                            {isVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <button
                            type="button"
                            aria-label={`Test ${slotLabel(slot)} key`}
                            disabled={test?.state === 'loading'}
                            onClick={() => void handleTest(item.provider, slot)}
                            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:border-indigo-400 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {test?.state === 'loading' ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <CheckCircle2 size={12} />
                            )}
                            Test
                          </button>

                          {keyState.source === 'db' && (
                            <>
                              {!awaitingConfirm ? (
                                <button
                                  type="button"
                                  aria-label={`Clear saved ${slotLabel(slot)} key`}
                                  onClick={() =>
                                    setConfirmClear((previous) => ({ ...previous, [id]: true }))
                                  }
                                  className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-2.5 py-1 text-xs font-bold text-rose-700 hover:bg-rose-50"
                                >
                                  Clear saved key
                                </button>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded-full border border-rose-300 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-800">
                                  Clear this key?
                                  <button
                                    type="button"
                                    onClick={() => void handleClear(item.provider, slot)}
                                    className="rounded-full bg-rose-600 px-2 py-0.5 text-xs font-bold text-white hover:bg-rose-700"
                                  >
                                    Confirm
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setConfirmClear((previous) => ({ ...previous, [id]: false }))
                                    }
                                    className="rounded-full px-1.5 py-0.5 text-xs font-bold text-rose-700 hover:bg-rose-100"
                                  >
                                    Cancel
                                  </button>
                                </span>
                              )}
                            </>
                          )}
                        </div>

                        {test?.state === 'done' && (
                          <p
                            role="status"
                            className={`mt-2 rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${
                              test.result.ok
                                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                                : 'border-amber-200 bg-amber-50 text-amber-900'
                            }`}
                          >
                            {test.result.ok ? 'Verified' : 'Failed'} · HTTP {test.result.status_code || '—'} ·{' '}
                            {Math.round(test.result.latency_ms)} ms · {test.result.message}
                          </p>
                        )}
                        {test?.state === 'error' && (
                          <p
                            role="alert"
                            className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-semibold text-rose-800"
                          >
                            {test.message}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5">
                <label className="inline-flex cursor-pointer items-start gap-2 text-xs font-semibold text-slate-700">
                  <input
                    type="checkbox"
                    checked={draft.autoFailoverKey}
                    onChange={(event) =>
                      updateDraft(item.provider, { autoFailoverKey: event.target.checked })
                    }
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600"
                  />
                  <span>
                    Auto-failover to the standby key
                    <span className="block font-medium text-slate-500">
                      Retry once with the other slot on HTTP 401, 403, or 429.
                    </span>
                  </span>
                </label>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={switching || !standbyState.configured}
                    title={
                      standbyState.configured
                        ? `Switch to the ${standbySlot} key`
                        : `Add the ${standbySlot} key first`
                    }
                    onClick={() => void handleSwitch(item.provider)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-xs font-bold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {switching ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    Use {slotLabel(standbySlot)} key
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void handleSave(item.provider)}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-1.5 text-xs font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                    Save {item.provider === 'cloudflare' ? 'Cloudflare' : item.provider === 'gemini' ? 'Gemini' : 'NVIDIA'} settings
                  </button>
                </div>
              </div>

              {!draft.enabled && (
                <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  This provider is disabled and will not receive requests, even if a key is configured.
                </p>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
