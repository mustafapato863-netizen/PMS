import { motion } from 'framer-motion';
import { useAuth } from '../../context/auth';

const steps = [
  ['authenticating', 'Authenticating'],
  ['loadingProfile', 'Loading profile'],
  ['loadingPermissions', 'Loading permissions'],
  ['loadingTeams', 'Loading assigned teams'],
  ['loadingNavigation', 'Preparing dashboard'],
  ['ready', 'Preparing dashboard'],
] as const;

const stepLabels = Object.fromEntries(steps);

export default function WorkspaceLoader() {
  const { initializationStatus } = useAuth();
  const currentStep = stepLabels[initializationStatus] || 'Preparing dashboard';
  const activeIndex = Math.max(0, steps.findIndex(([status]) => status === initializationStatus));
  const progress = ((activeIndex + 1) / steps.length) * 100;

  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-4"
      style={{
        background:
          'radial-gradient(circle at 30% 20%, var(--glow-blue), transparent 34%), radial-gradient(circle at 72% 76%, var(--glow-emerald), transparent 32%), linear-gradient(135deg, var(--bg-base), var(--bg-sunken))',
      }}
    >
      <motion.div
        aria-hidden="true"
        className="absolute h-56 w-56 rounded-full opacity-30 blur-3xl"
        style={{ background: 'var(--glow-indigo)' }}
        animate={{ scale: [1, 1.08, 1], opacity: [0.22, 0.34, 0.22] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
      />

      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
        className="glass-panel relative w-full max-w-[420px] overflow-hidden rounded-2xl px-7 py-8 text-center"
      >
        <motion.div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background:
              'linear-gradient(90deg, transparent, rgba(59,130,246,.65), rgba(16,185,129,.55), transparent)',
          }}
          animate={{ opacity: [0.35, 0.9, 0.35] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />

        <div className="mb-6 flex justify-center">
          <motion.div
            className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-emerald-500 text-lg font-extrabold text-white shadow-lg shadow-blue-500/20"
            animate={{ scale: [1, 1.04, 1], boxShadow: ['0 14px 32px rgba(59,130,246,.18)', '0 18px 42px rgba(16,185,129,.24)', '0 14px 32px rgba(59,130,246,.18)'] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
          >
            <motion.span
              className="absolute inset-0 rounded-2xl border border-white/35"
              animate={{ opacity: [0.7, 0.25, 0.7] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
            />
            SGH
          </motion.div>
        </div>

        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[var(--text-muted)]">SGH Hub</p>
        <h2 className="text-xl font-bold text-[var(--text-primary)]">Preparing your workspace</h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">{currentStep}</p>

        <div className="mt-7 h-1.5 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 via-indigo-500 to-emerald-400"
            initial={{ width: '12%' }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
          />
        </div>

        <div className="mt-5 flex justify-center gap-2">
          {steps.slice(0, -1).map(([status], index) => (
            <motion.span
              key={status}
              className="h-2 w-2 rounded-full"
              style={{
                background:
                  index <= activeIndex ? 'linear-gradient(135deg, #3B82F6, #10B981)' : 'var(--border-strong)',
              }}
              animate={index === activeIndex ? { scale: [1, 1.35, 1], opacity: [0.7, 1, 0.7] } : { scale: 1, opacity: 0.75 }}
              transition={{ duration: 1.2, repeat: index === activeIndex ? Infinity : 0, ease: 'easeInOut' }}
            />
          ))}
        </div>
      </motion.div>
    </div>
  );
}
