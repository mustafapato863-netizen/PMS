import './PageEnhancements.css';
/**
 * Team Management View
 * Admin page for managing teams (create, edit, delete, view).
 * Provides team onboarding workflow and configuration.
 */

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Settings, AlertCircle, Trash2, X } from 'lucide-react';
import TeamList from '../components/team-management/TeamList';
import TeamForm from '../components/team-management/TeamForm';
import TeamOnboarding from '../components/team-management/TeamOnboarding';
import { useTeamManagement } from '../hooks/useTeamManagement';
import type { CreateTeamRequest, Team } from '../hooks/useTeamManagement';

type ViewMode = 'list' | 'create' | 'edit' | 'onboarding';

export function TeamManagementView() {
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [teamToDelete, setTeamToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const {
    teams,
    isLoading,
    error,
    createTeam,
    updateTeam,
    deleteTeam,
    refreshTeams,
  } = useTeamManagement();

  const handleCreateTeam = async (formData: CreateTeamRequest) => {
    const success = await createTeam(formData);
    if (success) {
      setShowForm(false);
      setViewMode('list');
      await refreshTeams();
    }
  };

  const handleUpdateTeam = async (teamName: string, formData: CreateTeamRequest) => {
    const success = await updateTeam(teamName, formData);
    if (success) {
      setShowForm(false);
      setViewMode('list');
      setSelectedTeam(null);
      await refreshTeams();
    }
  };

  const handleDeleteTeam = async () => {
    if (!teamToDelete) return;
    setIsDeleting(true);
    try {
      const success = await deleteTeam(teamToDelete);
      if (success) {
        setViewMode('list');
        setSelectedTeam(null);
        setTeamToDelete(null);
        await refreshTeams();
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const handleEditTeam = (team: Team) => {
    setSelectedTeam(team);
    setViewMode('edit');
    setShowForm(true);
  };

  const handleStartOnboarding = (team: Team) => {
    setSelectedTeam(team);
    setViewMode('onboarding');
  };

  const handleBackToList = () => {
    setViewMode('list');
    setSelectedTeam(null);
    setShowForm(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="rf-page rf-page--team-management flex-1 w-full"
    >
      {/* Header */}
      <div className="rf-page-hero mb-6">
        <h1 className="text-3xl font-bold text-[var(--text-primary)] mb-2">
          Team Management
        </h1>
        <p className="text-[var(--text-secondary)]">
          Manage teams, configurations, and onboarding workflows
        </p>
      </div>

      {/* Error Display */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-3"
          role="alert"
        >
          <AlertCircle size={20} className="text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-700">Error</h3>
            <p className="text-sm text-red-600 mt-1">{error}</p>
          </div>
        </motion.div>
      )}

      {/* View: List */}
      {viewMode === 'list' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {/* Actions Bar */}
          <div className="rf-toolbar flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
            <div className="flex items-center gap-2">
              <Settings size={20} className="text-blue-500" />
              <span className="text-sm font-semibold text-[var(--text-secondary)]">
                {teams.length} team{teams.length !== 1 ? 's' : ''} configured
              </span>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => {
                setSelectedTeam(null);
                setViewMode('create');
                setShowForm(true);
              }}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white
                rounded-lg font-semibold transition-all shadow-sm"
            >
              <Plus size={16} />
              New Team
            </motion.button>
          </div>

          {/* Team List */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-[var(--text-muted)]">Loading teams...</div>
            </div>
          ) : teams.length === 0 ? (
            <div className="rf-empty-state text-center py-12 bg-[var(--bg-surface)]/50 rounded-2xl">
              <Settings size={48} className="text-[var(--text-muted)] mx-auto mb-4 opacity-50" />
              <p className="text-[var(--text-secondary)] font-medium">No teams yet</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">Click "New Team" to create one</p>
            </div>
          ) : (
            <TeamList
              teams={teams}
              onEdit={handleEditTeam}
              onDelete={setTeamToDelete}
              onOnboard={handleStartOnboarding}
            />
          )}
        </motion.div>
      )}

      {teamToDelete && (
        <div className="rf-modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            className="rf-modal-panel w-full max-w-md rounded-3xl border border-red-200 bg-[var(--bg-surface)] p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="team-delete-title"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-red-500/10 p-3 text-red-600">
                  <Trash2 size={18} />
                </div>
                <div>
                  <h3 id="team-delete-title" className="text-lg font-black text-[var(--text-primary)]">
                    Delete Team
                  </h3>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    This will remove <span className="font-bold text-[var(--text-primary)]">{teamToDelete}</span>.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => !isDeleting && setTeamToDelete(null)}
                className="rounded-xl p-2 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-sunken)]"
                aria-label="Close delete confirmation"
              >
                <X size={16} />
              </button>
            </div>

            <div className="rounded-2xl border border-red-200/70 bg-red-50/60 p-4 text-sm text-red-700">
              This action cannot be undone.
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setTeamToDelete(null)}
                disabled={isDeleting}
                className="rounded-xl border border-[var(--border-light)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteTeam}
                disabled={isDeleting}
                className="rounded-xl bg-red-600 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                {isDeleting ? 'Deleting...' : 'Delete Team'}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* View: Create/Edit Form */}
      {(viewMode === 'create' || viewMode === 'edit') && showForm && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
        >
          <TeamForm
            mode={viewMode === 'create' ? 'create' : 'edit'}
            initialData={selectedTeam ?? undefined}
            onSubmit={(formData) =>
              viewMode === 'create'
                ? handleCreateTeam(formData)
                : handleUpdateTeam(selectedTeam?.name || '', formData)
            }
            onCancel={handleBackToList}
            isLoading={isLoading}
          />
        </motion.div>
      )}

      {/* View: Onboarding */}
      {viewMode === 'onboarding' && selectedTeam && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
        >
          <TeamOnboarding team={selectedTeam} onComplete={handleBackToList} />
        </motion.div>
      )}
    </motion.div>
  );
}

export default TeamManagementView;
