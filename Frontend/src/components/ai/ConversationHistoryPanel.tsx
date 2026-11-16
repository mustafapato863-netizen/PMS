import { useEffect } from 'react';
import { Check, History, Loader2, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import type { AiConversationSummaryItem } from '../../features/ai/types';

interface ConversationHistoryPanelProps {
  isOpen: boolean;
  conversations: AiConversationSummaryItem[];
  activeConversationId: string | null;
  sendingByConvId: Record<string, boolean>;
  isLoading: boolean;
  errorMessage: string | null;
  confirmDeleteId: string | null;
  deletingConvId: string | null;
  onClose: () => void;
  onNewChat: () => void;
  onSelectConversation: (conversationId: string) => void;
  onRequestDelete: (conversationId: string) => void;
  onConfirmDelete: (conversationId: string) => void;
  onCancelDelete: () => void;
  onRetryLoad: () => void;
}

/**
 * Slim desktop conversation history rail and responsive `< lg` slide-over drawer.
 */
export default function ConversationHistoryPanel({
  isOpen,
  conversations,
  activeConversationId,
  sendingByConvId,
  isLoading,
  errorMessage,
  confirmDeleteId,
  deletingConvId,
  onClose,
  onNewChat,
  onSelectConversation,
  onRequestDelete,
  onConfirmDelete,
  onCancelDelete,
  onRetryLoad,
}: ConversationHistoryPanelProps) {
  useEffect(() => {
    if (!isOpen) return;
    const isDesktop =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(min-width: 1024px)').matches;
    if (isDesktop) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex lg:static lg:inset-auto lg:z-auto lg:w-64 lg:shrink-0 xl:w-72">
      {/* Mobile / tablet backdrop */}
      <button
        type="button"
        aria-label="Close recent chats backdrop"
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/35 backdrop-blur-[1px] transition-opacity lg:hidden"
      />

      <aside
        aria-label="Recent chats"
        data-testid="ai-recent-chats-panel"
        className="relative z-10 flex h-full w-72 max-w-[85vw] flex-col overflow-hidden border-r border-slate-200/80 bg-white shadow-xl lg:h-[calc(100dvh-108px)] lg:w-full lg:max-w-none lg:rounded-3xl lg:border lg:shadow-[0_10px_35px_rgb(15,23,42,0.06)]"
      >
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <History size={15} className="shrink-0 text-blue-600" />
            <h2 className="truncate text-sm font-extrabold text-slate-900">Recent chats</h2>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={onNewChat}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700"
            >
              <Plus size={12} />
              <span>New</span>
            </button>
            <button
              type="button"
              aria-label="Close recent chats"
              onClick={onClose}
              className="inline-flex items-center justify-center rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:hidden"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2.5">
          {isLoading && conversations.length === 0 ? (
            <div className="space-y-2 p-2" aria-label="Loading recent chats">
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
              <div className="h-12 animate-pulse rounded-xl bg-slate-100" />
            </div>
          ) : errorMessage && conversations.length === 0 ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50/80 p-4 text-center text-xs text-rose-800">
              <p className="font-semibold">{errorMessage}</p>
              <button
                type="button"
                onClick={onRetryLoad}
                className="mt-2 inline-flex items-center gap-1 rounded-full border border-rose-300 bg-white px-3 py-1 text-xs font-bold text-rose-700 hover:bg-rose-100"
              >
                <RotateCcw size={12} />
                <span>Retry</span>
              </button>
            </div>
          ) : conversations.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-4 text-center text-xs font-medium text-slate-500">
              No saved conversations yet. Start a chat to save your history.
            </div>
          ) : (
            conversations.map((conv) => {
              const isActive = activeConversationId === conv.conversation_id;
              const bgSending = Boolean(sendingByConvId[conv.conversation_id]);
              const isConfirming = confirmDeleteId === conv.conversation_id;
              return (
                <div
                  key={conv.conversation_id}
                  data-testid={`ai-recent-chat-${conv.conversation_id}`}
                  className={`group rounded-2xl border p-2.5 transition-colors ${
                    isActive
                      ? 'border-blue-300 bg-blue-50/70'
                      : 'border-slate-200/80 bg-white hover:border-slate-300 hover:bg-slate-50/70'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => onSelectConversation(conv.conversation_id)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="truncate text-xs font-bold text-slate-900">
                        {conv.title || 'New conversation'}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                        <span>
                          {conv.turn_count} {conv.turn_count === 1 ? 'turn' : 'turns'}
                        </span>
                        {!conv.has_restricted_turns && conv.last_scope_banner && (
                          <span className="truncate text-slate-500">
                            · {conv.last_scope_banner}
                          </span>
                        )}
                        {conv.has_restricted_turns && (
                          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-800">
                            Restricted
                          </span>
                        )}
                        {bgSending && (
                          <span className="inline-flex items-center gap-1 rounded bg-sky-100 px-1.5 py-0.5 text-xs font-semibold text-sky-700">
                            <Loader2 size={11} className="animate-spin" />
                            <span>Running…</span>
                          </span>
                        )}
                      </div>
                    </button>

                    {!isConfirming ? (
                      <button
                        type="button"
                        aria-label={`Delete conversation ${conv.title || conv.conversation_id}`}
                        onClick={() => onRequestDelete(conv.conversation_id)}
                        className="rounded-lg p-1 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-600"
                      >
                        <Trash2 size={13} />
                      </button>
                    ) : (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          aria-label="Confirm delete conversation"
                          disabled={deletingConvId === conv.conversation_id}
                          onClick={() => onConfirmDelete(conv.conversation_id)}
                          className="inline-flex items-center gap-0.5 rounded-lg bg-rose-600 px-2 py-1 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                        >
                          <Check size={12} />
                          <span>Confirm</span>
                        </button>
                        <button
                          type="button"
                          aria-label="Cancel delete conversation"
                          onClick={onCancelDelete}
                          className="inline-flex items-center gap-0.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-bold text-slate-600 hover:bg-slate-100"
                        >
                          <X size={12} />
                          <span>Cancel</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}
