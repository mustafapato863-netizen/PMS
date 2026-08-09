/**
 * Notification Center Panel
 * Displays list of notifications with actions
 */

import { X, CheckCheck, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '../../store/appStore';
import NotificationItem from './NotificationItem';

interface NotificationCenterProps {
  onClose?: () => void;
}

export function NotificationCenter({ onClose }: NotificationCenterProps) {
  const {
    notifications,
    unreadCount,
    markAllRead,
    clearNotifications,
    removeNotification,
  } = useAppStore();

  const sortedNotifications = [...notifications].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return (
    <div
      className="w-96 max-h-[600px] bg-[var(--bg-surface)]/95 backdrop-blur-xl rounded-2xl
        shadow-xl border border-[var(--border-light)] flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-[var(--border-light)] flex-shrink-0">
        <div className="flex-1">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Notifications</h2>
          {unreadCount > 0 && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              {unreadCount} unread
            </p>
          )}
        </div>

        {/* Close button */}
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={onClose}
          aria-label="Close notifications"
          className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]
            hover:bg-[var(--bg-sunken)] rounded-lg transition-colors"
        >
          <X size={16} aria-hidden="true" />
        </motion.button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {sortedNotifications.length === 0 ? (
          <div className="p-8 flex flex-col items-center justify-center text-center min-h-[200px]">
            <div className="text-3xl mb-2">🎉</div>
            <p className="text-sm text-[var(--text-muted)]">
              No notifications yet
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              You're all caught up!
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-light)]">
            <AnimatePresence mode="popLayout">
              {sortedNotifications.map((notification) => (
                <motion.div
                  key={notification.id}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <NotificationItem
                    notification={notification}
                    onRemove={() => removeNotification(notification.id)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Footer */}
      {sortedNotifications.length > 0 && (
        <div
          className="flex items-center justify-between gap-2 p-3 border-t border-[var(--border-light)]
            bg-[var(--bg-base)]/50 flex-shrink-0"
        >
          <motion.button
            whileHover={{ backgroundColor: 'rgba(59, 130, 246, 0.1)' }}
            onClick={markAllRead}
            disabled={unreadCount === 0}
            aria-label="Mark all as read"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold
              text-blue-600 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed
              hover:disabled:bg-transparent"
          >
            <CheckCheck size={13} aria-hidden="true" />
            Mark all read
          </motion.button>

          <motion.button
            whileHover={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}
            onClick={clearNotifications}
            aria-label="Clear all notifications"
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold
              text-red-600 rounded-lg transition-all hover:bg-red-500/10"
          >
            <Trash2 size={13} aria-hidden="true" />
            Clear all
          </motion.button>
        </div>
      )}
    </div>
  );
}

export default NotificationCenter;
