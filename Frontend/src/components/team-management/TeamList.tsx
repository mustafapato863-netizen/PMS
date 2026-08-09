/**
 * Team List Component
 * Displays teams in a grid with actions (edit, delete, onboard).
 */

import { motion } from 'framer-motion';
import { Edit2, Trash2, Play, Globe, Users } from 'lucide-react';
import type { Team } from '../../hooks/useTeamManagement';

interface TeamListProps {
  teams: Team[];
  onEdit: (team: Team) => void;
  onDelete: (teamName: string) => void;
  onOnboard: (team: Team) => void;
}

export function TeamList({ teams, onEdit, onDelete, onOnboard }: TeamListProps) {
  const activeTeams = teams.filter((t) => t.is_active);
  const inactiveTeams = teams.filter((t) => !t.is_active);

  const TeamCard = ({ team, index }: { team: Team; index: number }) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
      className={`p-6 rounded-xl border-2 transition-all ${
        team.is_active
          ? 'bg-[var(--bg-surface)]/60 border-[var(--border-light)] hover:border-blue-500/50'
          : 'bg-[var(--bg-surface)]/30 border-[var(--border-light)] opacity-50'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-bold text-[var(--text-primary)]">{team.display_name}</h3>
            {!team.is_active && (
              <span className="px-2 py-0.5 text-xs font-semibold bg-red-500/20 text-red-600 rounded-full">
                Inactive
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--text-muted)] font-mono">{team.name}</p>
        </div>

        {/* Region Badge */}
        <div className="px-2.5 py-1 bg-blue-500/10 rounded-lg">
          <div className="flex items-center gap-1 text-xs font-semibold text-blue-600">
            <Globe size={12} />
            {team.region}
          </div>
        </div>
      </div>

      {/* Description */}
      {team.description && (
        <p className="text-sm text-[var(--text-secondary)] mb-4 line-clamp-2">
          {team.description}
        </p>
      )}

      {/* Team Lead */}
      {team.team_lead && (
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mb-4">
          <Users size={14} />
          <span>Lead: {team.team_lead}</span>
        </div>
      )}

      {/* KPI Keys */}
      {team.kpi_keys && team.kpi_keys.length > 0 && (
        <div className="mb-4">
          <div className="flex flex-wrap gap-1">
            {team.kpi_keys.map((kpi) => (
              <span
                key={kpi}
                className="px-2 py-1 text-xs font-medium bg-[var(--bg-base)]/50 text-[var(--text-secondary)]
                  rounded border border-[var(--border-light)]"
              >
                {kpi}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-4 border-t border-[var(--border-light)]">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => onEdit(team)}
          disabled={!team.is_active}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold
            text-blue-600 bg-blue-500/10 hover:bg-blue-500/20 rounded-lg transition-all
            disabled:opacity-50 disabled:cursor-not-allowed"
          title="Edit team configuration"
        >
          <Edit2 size={14} />
          Edit
        </motion.button>

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => onOnboard(team)}
          disabled={!team.is_active}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold
            text-green-600 bg-green-500/10 hover:bg-green-500/20 rounded-lg transition-all
            disabled:opacity-50 disabled:cursor-not-allowed"
          title="Start onboarding workflow"
        >
          <Play size={14} />
          Onboard
        </motion.button>

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => onDelete(team.name)}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold
            text-red-600 bg-red-500/10 hover:bg-red-500/20 rounded-lg transition-all"
          title="Delete team"
        >
          <Trash2 size={14} />
          Delete
        </motion.button>
      </div>
    </motion.div>
  );

  return (
    <div className="space-y-8">
      {/* Active Teams */}
      {activeTeams.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">
            Active Teams ({activeTeams.length})
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeTeams.map((team, index) => (
              <TeamCard key={team.name} team={team} index={index} />
            ))}
          </div>
        </div>
      )}

      {/* Inactive Teams */}
      {inactiveTeams.length > 0 && (
        <div>
          <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">
            Inactive Teams ({inactiveTeams.length})
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {inactiveTeams.map((team, index) => (
              <TeamCard key={team.name} team={team} index={activeTeams.length + index} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default TeamList;
