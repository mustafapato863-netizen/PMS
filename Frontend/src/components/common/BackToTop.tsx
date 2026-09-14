/**
 * Back-to-Top floating button.
 *
 * Appears after the user scrolls past a configurable threshold and
 * smoothly scrolls the page back to the top on click.
 */
import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp } from 'lucide-react';

interface BackToTopProps {
  /** Pixel offset before the button becomes visible. @default 400 */
  threshold?: number;
}

export default function BackToTop({ threshold = 400 }: BackToTopProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > threshold);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [threshold]);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.button
          key="back-to-top"
          type="button"
          onClick={scrollToTop}
          aria-label="Scroll to top"
          initial={{ opacity: 0, scale: 0.8, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.8, y: 10 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="fixed bottom-20 right-4 z-[9990] grid h-11 w-11 place-items-center rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-secondary)] shadow-lg backdrop-blur-sm transition-colors hover:border-blue-500/30 hover:text-blue-600 hover:shadow-xl focus-visible:outline-2 focus-visible:outline-blue-500 dark:bg-slate-900/90 dark:hover:text-blue-400"
        >
          <ArrowUp size={18} />
        </motion.button>
      )}
    </AnimatePresence>
  );
}
