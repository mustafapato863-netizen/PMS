/**
 * Team Onboarding Component
 * Displays onboarding checklist and workflow for new teams.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Circle, AlertCircle, Play, CheckCircle2 } from 'lucide-react';
import { useStartOnboarding, useOnboardingStatus } from '../../hooks/useTeamManagement';
import { ListLoadingSkeleton } from '../common/SkeletonLoader';

interface TeamOnboardingProps {
  team: { name: string; display_name?: string };
  onComplete: () => void;
}

export function TeamOnboarding({ team, onComplete }: TeamOnboardingProps) {
  const [isStarting, setIsStarting] = useState(false);
  const startOnboardingMutation = useStartOnboarding();
  const { data: onboardingStatus } = useOnboardingStatus(team.name);

  // Use API response if available, otherwise show empty state
  const steps = onboardingStatus?.steps || [];
  const currentStep = onboardingStatus?.current_step || 0;
  const isRunning = onboardingStatus?.status === 'in_progress';
  const allComplete = onboardingStatus?.status === 'completed';
  const completionPercent = Math.round((steps.filter((step) => step.completed).length / (steps.length || 1)) * 100);

  const handleStartOnboarding = async () => {
    setIsStarting(true);
    try {
      await startOnboardingMutation.mutateAsync({
        teamName: team.name,
        autoProceed: true,
      });
    } catch (error) {
      console.error('Failed to start onboarding:', error);
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="max-w-2xl"
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={onComplete}
          className="p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]
            hover:bg-[var(--bg-sunken)] rounded-lg transition-all"
        >
          <ArrowLeft size={20} />
        </motion.button>
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">
            Onboard {team.display_name}
          </h2>
          <p className="text-sm text-[var(--text-muted)]">
            Follow this checklist to set up your new team
          </p>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-[var(--text-secondary)]">Progress</span>
          <span className="text-sm font-bold text-blue-600">{completionPercent}%</span>
        </div>
        <div className="w-full h-3 bg-[var(--bg-base)] rounded-full overflow-hidden border border-[var(--border-light)]">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${completionPercent}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="h-full bg-gradient-to-r from-blue-600 to-blue-400"
          />
        </div>
      </div>

      {/* Onboarding Steps */}
      {steps.length > 0 ? (
        <div className="space-y-3 mb-8">
          <AnimatePresence>
            {steps.map((step, index) => (
              <motion.div
                key={step.step_number}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                className={`p-4 rounded-xl border-2 transition-all ${
                  step.completed
                    ? 'bg-green-500/10 border-green-500/30'
                    : index === currentStep && isRunning
                    ? 'bg-blue-500/10 border-blue-500/30'
                    : 'bg-[var(--bg-surface)]/60 border-[var(--border-light)]'
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div className="mt-1">
                    {step.completed ? (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: 'spring', stiffness: 200 }}
                      >
                        <CheckCircle2 size={24} className="text-green-600" />
                      </motion.div>
                    ) : index === currentStep && isRunning ? (
                      <motion.div animate={{ rotate: 360 }} transition={{ duration: 2, repeat: Infinity }}>
                        <Circle size={24} className="text-blue-600" />
                      </motion.div>
                    ) : (
                      <Circle size={24} className="text-[var(--text-muted)]" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-[var(--text-primary)]">
                        Step {step.step_number}: {step.name}
                      </h3>
                    </div>
                    <p className="text-sm text-[var(--text-secondary)]">{step.description}</p>

                    {/* Status */}
                    {step.completed && (
                      <motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-xs text-green-600 font-medium mt-2"
                      >
                        ✓ Completed
                      </motion.p>
                    )}
                    {index === currentStep && isRunning && (
                      <motion.p
                        animate={{ opacity: [0.5, 1, 0.5] }}
                        transition={{ duration: 1.5, repeat: Infinity }}
                        className="text-xs text-blue-600 font-medium mt-2"
                      >
                        Running...
                      </motion.p>
                    )}
                    {step.error && (
                      <motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-xs text-red-600 font-medium mt-2"
                      >
                        ✗ Error: {step.error}
                      </motion.p>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <div className="mb-8 rounded-lg border border-[var(--border-light)] bg-[var(--bg-base)] p-4">
          <ListLoadingSkeleton rows={4} label="Loading onboarding workflow" />
        </div>
      )}

      {/* Actions */}
      {!allComplete ? (
        <div className="flex items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onComplete}
            className="flex-1 px-4 py-3 bg-[var(--bg-base)] border border-[var(--border-light)]
              text-[var(--text-secondary)] font-semibold rounded-lg hover:bg-[var(--bg-sunken)]
              transition-all disabled:opacity-50"
            disabled={isRunning || isStarting}
          >
            Cancel
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleStartOnboarding}
            disabled={isRunning || isStarting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-blue-600
              hover:bg-blue-700 text-white font-semibold rounded-lg transition-all disabled:opacity-50"
          >
            <Play size={16} />
            {isRunning || isStarting ? 'Running...' : 'Start Onboarding'}
          </motion.button>
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center py-8 bg-green-500/10 rounded-xl border-2 border-green-500/30"
        >
          <CheckCircle2 size={48} className="text-green-600 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-[var(--text-primary)] mb-1">
            Onboarding Complete!
          </h3>
          <p className="text-sm text-[var(--text-secondary)] mb-6">
            {team.display_name} is ready to use
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onComplete}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold
              rounded-lg transition-all"
          >
            Done
          </motion.button>
        </motion.div>
      )}

      {/* Info */}
      <div className="mt-8 p-4 bg-blue-500/10 rounded-lg border border-blue-500/20 flex items-start gap-3">
        <AlertCircle size={20} className="text-blue-600 shrink-0 mt-0.5" />
        <div className="text-sm text-blue-700">
          <p className="font-medium">Onboarding Process</p>
          <p className="mt-1">
            This process will automatically set up directories, seed data, and configure alerts for the team.
            No action required.
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export default TeamOnboarding;
