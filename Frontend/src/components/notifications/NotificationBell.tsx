/**
 * Enhanced Notification Bell Component
 * Shows unread notification count and opens notification center
 */

import { useState, useEffect } from 'react';
import { Bell } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '../../store/appStore';
import NotificationCenter from './NotificationCenter';

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const { unreadCount } = useAppStore();

  // Close notification center when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-notification-bell]')) {
        setIsOpen(false);
      }
    };

    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, [isOpen]);

  return (
    <div data-notification-bell className="relative" role="region" aria-label="Notifications">
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(!isOpen)}
        aria-label={`Notifications — ${unreadCount} unread`}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className="relative p-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-surface)]/40 backdrop-blur-sm
          rounded-xl border border-[var(--border-light)] hover:bg-[var(--bg-surface)]/80 transition-all"
      >
        <Bell size={16} aria-hidden="true" />

        {/* Notification badge */}
        <AnimatePresence>
          {unreadCount > 0 && (
            <motion.span
              key="badge"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full
                ring-[1.5px] ring-[var(--bg-surface)]"
              aria-hidden="true"
            />
          )}
        </AnimatePresence>
      </motion.button>

      {/* Notification Center Popover */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsOpen(false)}
              aria-hidden="true"
            />

            {/* Panel */}
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.95 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              role="dialog"
              aria-label="Notification center"
              className="absolute right-0 mt-2 z-50"
            >
              <NotificationCenter onClose={() => setIsOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

export default NotificationBell;
