import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';

interface ThemeToggleProps {
  /** 'icon' = compact icon-only button (for header/sidebar). Default. */
  variant?: 'icon' | 'pill';
}

const ThemeToggle = ({ variant = 'icon' }: ThemeToggleProps) => {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === 'dark';

  if (variant === 'pill') {
    return (
      <button
        onClick={toggleTheme}
        aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
        title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
        className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-200 cursor-pointer w-full"
        style={{
          background: 'var(--sidebar-hover-bg)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border-light)',
        }}
      >
        {/* Track */}
        <div
          className="relative flex-shrink-0"
          style={{
            width: '36px',
            height: '20px',
            borderRadius: '999px',
            background: isDark
              ? 'linear-gradient(135deg, #1e3a5f, #3b82f6)'
              : 'linear-gradient(135deg, #fbbf24, #f59e0b)',
            transition: 'background 0.4s ease',
            border: '1.5px solid rgba(255,255,255,0.15)',
            boxShadow: isDark
              ? 'inset 0 1px 3px rgba(0,0,0,0.4)'
              : 'inset 0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          <motion.div
            layout
            transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            style={{
              position: 'absolute',
              top: '2px',
              left: isDark ? '18px' : '2px',
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              background: '#fff',
              boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
            }}
          />
        </div>
        <span style={{ color: 'var(--text-primary)' }}>
          {isDark ? 'Dark Mode' : 'Light Mode'}
        </span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={theme}
            initial={{ opacity: 0, scale: 0.6, rotate: -30 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.6, rotate: 30 }}
            transition={{ duration: 0.2 }}
            className="ml-auto"
          >
            {isDark
              ? <Moon size={14} className="text-blue-400" />
              : <Sun size={14} className="text-amber-500" />
            }
          </motion.div>
        </AnimatePresence>
      </button>
    );
  }

  // Default icon-only variant
  return (
    <motion.button
      onClick={toggleTheme}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.92 }}
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      className="theme-toggle"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={theme}
          initial={{ opacity: 0, scale: 0.5, rotate: -90 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          exit={{ opacity: 0, scale: 0.5, rotate: 90 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        >
          {isDark
            ? <Sun size={16} className="text-amber-400" />
            : <Moon size={16} className="text-slate-500" />
          }
        </motion.div>
      </AnimatePresence>
    </motion.button>
  );
};

export default ThemeToggle;
