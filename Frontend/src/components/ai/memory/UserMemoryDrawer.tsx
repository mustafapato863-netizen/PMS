/** "My Profile & Memory" drawer — view and clear personal AI memory. */

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Brain, Loader2, RefreshCw, Trash2, X } from 'lucide-react';
import { apiFetch } from '../../../lib/apiClient';

interface MemoryData {
  preferences: Record<string, unknown>;
  query_patterns: Record<string, unknown>;
  interaction_summary: string;
  feedback_signals: Record<string, unknown>;
}

interface UserMemoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function UserMemoryDrawer({ isOpen, onClose }: UserMemoryDrawerProps) {
  const [memory, setMemory] = useState<MemoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ memory: MemoryData | null }>('/api/ai/memory/me');
      setMemory(res.memory);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load your memory.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [isOpen, load]);

  const clearAll = useCallback(async () => {
    setLoading(true);
    try {
      await apiFetch('/api/ai/memory/me', { method: 'DELETE' });
      setMemory(null);
      setConfirmClear(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to clear your memory.');
    } finally {
      setLoading(false);
    }
  }, []);

  if (!isOpen) return null;

  const itemCount = memory
    ? Object.keys(memory.preferences || {}).length +
      Object.keys(memory.query_patterns || {}).length +
      Object.keys(memory.feedback_signals || {}).length +
      (memory.interaction_summary ? 1 : 0)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30" onMouseDown={onClose} data-testid="user-memory-drawer">
      <aside
        className="flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <Brain size={18} className="text-blue-600" />
            <div>
              <h2 className="text-sm font-bold text-slate-900">My Profile & Memory</h2>
              <p className="text-xs text-slate-500">What your AI assistant remembers about you</p>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" /> Loading…
            </div>
          ) : error ? (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              <AlertCircle size={16} className="mt-0.5 shrink-0" /> {error}
            </div>
          ) : !memory || itemCount === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-center">
              <Brain size={22} className="mx-auto text-slate-300" />
              <p className="mt-2 text-sm font-semibold text-slate-700">No memory yet</p>
              <p className="mt-1 text-xs text-slate-500">As you chat, your assistant will learn your preferences and focus areas.</p>
            </div>
          ) : (
            <div className="space-y-4">
              <MemorySection title="Preferences" data={memory.preferences} />
              <MemorySection title="Focus & patterns" data={memory.query_patterns} />
              {memory.interaction_summary && (
                <div className="rounded-xl border border-slate-200 p-3">
                  <h3 className="text-xs font-bold uppercase tracking-wide text-slate-400">Interaction summary</h3>
                  <p className="mt-1 text-sm text-slate-700">{memory.interaction_summary}</p>
                </div>
              )}
              <MemorySection title="Feedback" data={memory.feedback_signals} />
            </div>
          )}
        </div>

        <footer className="border-t border-slate-200 px-5 py-4">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>{itemCount} item(s) stored</span>
            <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1 font-semibold text-blue-600 hover:underline">
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
          {confirmClear ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void clearAll()}
                className="flex-1 rounded-lg bg-rose-600 px-3 py-2 text-sm font-bold text-white hover:bg-rose-700"
              >
                Yes, clear all
              </button>
              <button
                type="button"
                onClick={() => setConfirmClear(false)}
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              disabled={!memory || itemCount === 0}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-bold text-rose-700 hover:border-rose-400 disabled:opacity-40"
            >
              <Trash2 size={14} /> Clear all my memory
            </button>
          )}
        </footer>
      </aside>
    </div>
  );
}

function MemorySection({ title, data }: { title: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data || {});
  if (entries.length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-400">{title}</h3>
      <ul className="mt-2 space-y-1.5">
        {entries.map(([key, value]) => (
          <li key={key} className="flex items-start justify-between gap-3 text-sm">
            <span className="text-slate-600">{humanize(key)}</span>
            <span className="max-w-[55%] break-words text-right font-semibold text-slate-800">{formatValue(value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function humanize(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  return String(value);
}
