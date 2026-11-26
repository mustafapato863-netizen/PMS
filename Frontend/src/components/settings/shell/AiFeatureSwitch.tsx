import { ClipboardList, MessageSquareWarning, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAiAvailability } from '../../../features/ai/aiAvailabilityContext';
import type { AiAccessTier } from '../../../types';
import { settingsPathFor } from './settingsNavigation';

const ACCESS_TIER_OPTIONS: Array<{ value: AiAccessTier; label: string; description: string }> = [
  {
    value: 'admin_only',
    label: 'Administrators only (Pilot)',
    description: 'Only Admin accounts can access PMS AI.',
  },
  {
    value: 'managers_and_admins',
    label: 'Managers & Administrators',
    description: 'Admins, Executives, Directors, Managers, and Function Viewers.',
  },
  {
    value: 'all_authenticated_users',
    label: 'All authenticated users',
    description: 'Every signed-in user, including self-scoped Agents (360° Coach).',
  },
];

/** Administration controls. Visible while AI itself is hidden from every role, including Admin. */
export function AiFeatureSwitch() {
  const {
    enabled,
    accessTier,
    correctiveActionPilotEnabled,
    ready,
    saving,
    error,
    setEnabled,
    setAccessTier,
    setCorrectiveActionPilotEnabled,
  } = useAiAvailability();
  const on = ready && enabled;
  const pilotOn = ready && correctiveActionPilotEnabled;
  const activeTierMeta = ACCESS_TIER_OPTIONS.find((opt) => opt.value === accessTier) ?? ACCESS_TIER_OPTIONS[0];

  return (
    <div className="flex flex-col gap-3">
      <section
        aria-labelledby="ai-feature-heading"
        className="flex flex-col gap-3 rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-4 shadow-[var(--exec-card-shadow)]"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--exec-tile-bg)] text-[var(--insights-accent)]">
              <Sparkles size={18} aria-hidden="true" />
            </span>
            <div className="min-w-0 space-y-0.5">
              <h2 id="ai-feature-heading" className="text-sm font-bold tracking-tight text-[var(--insights-heading)]">
                PMS AI
              </h2>
              <p className="text-[13px] leading-5 text-[var(--text-secondary)]">
                {on
                  ? 'On for every signed-in role permitted by the selected rollout tier.'
                  : 'Off for every user, including administrators. The assistant, Ask AI, and the PMS AI page stay hidden.'}
              </p>
              <Link
                to={settingsPathFor('ai_feedback')}
                className="mt-1 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--insights-accent)] hover:underline"
              >
                <MessageSquareWarning size={13} aria-hidden="true" />
                <span>Review AI feedback &amp; approved patterns</span>
              </Link>
              {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-label="Enable PMS AI"
            disabled={!ready || saving}
            onClick={() => void setEnabled(!enabled).catch(() => undefined)}
            className={`inline-flex h-9 w-[4.5rem] shrink-0 items-center rounded-full p-1 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)] disabled:opacity-60 ${
              on ? 'justify-end bg-[var(--sgh-cyan-primary,#00A3E0)]' : 'justify-start bg-[var(--bg-sunken)]'
            }`}
          >
            <span className="sr-only">{on ? 'On' : 'Off'}</span>
            <span className="grid h-7 min-w-7 place-items-center rounded-full bg-white px-1.5 text-xs font-bold text-slate-900 shadow-sm">
              {saving ? '…' : on ? 'On' : 'Off'}
            </span>
          </button>
        </div>

        {/* Staged Rollout Access Tier Control */}
        <div className="flex flex-col gap-2 border-t border-[var(--exec-card-border)] pt-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-[var(--insights-accent)]" aria-hidden="true" />
            <div>
              <label htmlFor="ai-access-tier-select" className="text-xs font-bold text-[var(--insights-heading)]">
                Access rollout tier
              </label>
              <p className="text-xs text-[var(--text-secondary)]">{activeTierMeta.description}</p>
            </div>
          </div>
          <select
            id="ai-access-tier-select"
            aria-label="PMS AI access rollout tier"
            disabled={!ready || saving}
            value={accessTier}
            onChange={(e) => void setAccessTier(e.target.value as AiAccessTier).catch(() => undefined)}
            className="w-full rounded-xl border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--insights-heading)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--sgh-cyan-primary)] disabled:opacity-60 sm:w-64"
          >
            {ACCESS_TIER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section
        aria-labelledby="ai-pilot-heading"
        className="flex flex-col gap-3 rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-4 shadow-[var(--exec-card-shadow)] sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--exec-tile-bg)] text-[var(--insights-accent)]">
            <ClipboardList size={18} aria-hidden="true" />
          </span>
          <div className="min-w-0 space-y-0.5">
            <h2 id="ai-pilot-heading" className="text-sm font-bold tracking-tight text-[var(--insights-heading)]">
              Contextual Corrective-Action Suggestions (Pilot)
            </h2>
            <p className="text-[13px] leading-5 text-[var(--text-secondary)]">
              {pilotOn
                ? 'Pilot on for administrators only. Suggestions use authorized PMS evidence and must be reviewed and explicitly saved; nothing is saved automatically.'
                : 'Pilot off. Standalone AI Workspace stays hidden whether this pilot is on or off.'}
            </p>
            {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={pilotOn}
          aria-label="Enable corrective-action pilot"
          disabled={!ready || saving}
          onClick={() => void setCorrectiveActionPilotEnabled(!correctiveActionPilotEnabled).catch(() => undefined)}
          className={`inline-flex h-9 w-[4.5rem] shrink-0 items-center rounded-full p-1 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)] disabled:opacity-60 ${
            pilotOn ? 'justify-end bg-[var(--sgh-cyan-primary,#00A3E0)]' : 'justify-start bg-[var(--bg-sunken)]'
          }`}
        >
          <span className="sr-only">{pilotOn ? 'On' : 'Off'}</span>
          <span className="grid h-7 min-w-7 place-items-center rounded-full bg-white px-1.5 text-xs font-bold text-slate-900 shadow-sm">
            {saving ? '…' : pilotOn ? 'On' : 'Off'}
          </span>
        </button>
      </section>
    </div>
  );
}
