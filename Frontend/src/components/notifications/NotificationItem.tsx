/**
 * Individual Notification Item Component
 * Displays a single notification with type-specific styling
 */

import { motion } from 'framer-motion';
import {
  X,
  Check,
  AlertCircle,
  CheckCircle,
  Info,
  Upload,
  ClipboardList,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { type Notification, useAppStore } from '../../store/appStore';

interface NotificationItemProps {
  notification: Notification;
  onRemove?: () => void;
}

const NOTIFICATION_ICONS: Record<Notification['type'], React.ComponentType<{ size: number; className?: string }>> = {
  error: AlertCircle,
  success: CheckCircle,
  info: Info,
  upload: Upload,
  action: ClipboardList,
};

const NOTIFICATION_COLORS: Record<Notification['type'], { bg: string; border: string; icon: string; text: string }> = {
  error: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/20',
    icon: 'text-red-600 dark:text-red-400',
    text: 'text-red-900 dark:text-red-100',
  },
  success: {
    bg: 'bg-green-500/10',
    border: 'border-green-500/20',
    icon: 'text-green-600 dark:text-green-400',
    text: 'text-green-900 dark:text-green-100',
  },
  info: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/20',
    icon: 'text-blue-600 dark:text-blue-400',
    text: 'text-blue-900 dark:text-blue-100',
  },
  upload: {
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/20',
    icon: 'text-purple-600 dark:text-purple-400',
    text: 'text-purple-900 dark:text-purple-100',
  },
  action: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    icon: 'text-amber-600 dark:text-amber-400',
    text: 'text-amber-900 dark:text-amber-100',
  },
};

export function NotificationItem({ notification, onRemove }: NotificationItemProps) {
  const { markNotificationAsRead } = useAppStore();
  const IconComponent = NOTIFICATION_ICONS[notification.type];
  const colors = NOTIFICATION_COLORS[notification.type];
  const timeAgo = formatDistanceToNow(new Date(notification.timestamp), { addSuffix: true });

  const handleClick = () => {
    // Only mark as read, no navigation
    if (!notification.read) {
      markNotificationAsRead(notification.id);
    }
  };

  return (
    <motion.div
      whileHover={{ backgroundColor: 'rgba(0, 0, 0, 0.02)' }}
      className={`p-4 flex gap-3 items-start ${colors.bg} border-l-4 ${colors.border} transition-colors\n        hover:bg-[var(--bg-sunken)]/50 group cursor-pointer`}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyPress={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          handleClick();
        }
      }}
    >
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        <IconComponent size={18} className={colors.icon} aria-hidden="true" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium ${colors.text} line-clamp-2`}>{notification.message}</p>
        {notification.meta && (
          <p className="text-xs text-[var(--text-muted)] mt-1 font-medium">
            {notification.meta.startsWith('By ') ? notification.meta : `By ${notification.meta}`}
          </p>
        )}
        <p className="text-xs text-[var(--text-muted)] mt-1">{timeAgo}</p>
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1">
        {!notification.read && (
          <motion.button
            whileHover={{ scale: 1.15 }}
            whileTap={{ scale: 0.9 }}
            onClick={(e) => {
              e.stopPropagation();
              markNotificationAsRead(notification.id);
            }}
            aria-label="Mark as read"
            className="p-1 text-[var(--text-muted)] hover:text-blue-600 hover:bg-blue-500/10\n              rounded-lg transition-colors opacity-0 group-hover:opacity-100"
          >
            <Check size={14} aria-hidden="true" />
          </motion.button>
        )}

        <motion.button
          whileHover={{ scale: 1.15 }}
          whileTap={{ scale: 0.9 }}
          onClick={(e) => {
            e.stopPropagation();
            onRemove?.();
          }}
          aria-label="Remove notification"
          className="p-1 text-[var(--text-muted)] hover:text-red-600 hover:bg-red-500/10\n            rounded-lg transition-colors opacity-0 group-hover:opacity-100"
        >
          <X size={14} aria-hidden="true" />
        </motion.button>
      </div>
    </motion.div>
  );
}

export default NotificationItem;
