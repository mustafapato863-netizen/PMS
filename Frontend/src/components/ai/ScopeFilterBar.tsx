import { Building2, Layers, Users } from 'lucide-react';
import AiScopeDropdown from './AiScopeDropdown';

interface TeamOption {
  value: string;
  label: string;
  badge?: string;
}

interface ScopeFilterBarProps {
  availableFunctions: string[];
  selectedFunction: string | null | undefined;
  availableRegions: string[];
  selectedRegion: string | null;
  availablePositions: string[];
  selectedPosition: string | null;
  availableTeams: TeamOption[];
  selectedTeam: string;
  availableBranches: string[];
  selectedBranch: string;
  availableLevels: string[];
  selectedLevel: string;
  answerDetail: 'auto' | 'brief' | 'details';
  onFilterChange: (
    key: 'function' | 'team' | 'branch' | 'performance_level' | 'region' | 'position',
    value: string,
  ) => void;
  onChangeAnswerDetail: (mode: 'brief' | 'details') => void;
  className?: string;
}

/**
 * Responsive scope selector and response-detail toggle bar for the PMS AI header.
 */
export default function ScopeFilterBar({
  availableFunctions,
  selectedFunction,
  availableRegions,
  selectedRegion,
  availablePositions,
  selectedPosition,
  availableTeams,
  selectedTeam,
  availableBranches,
  selectedBranch,
  availableLevels,
  selectedLevel,
  answerDetail,
  onFilterChange,
  onChangeAnswerDetail,
  className = '',
}: ScopeFilterBarProps) {
  return (
    <div className={`min-w-0 flex-wrap items-center gap-1.5 ${className}`}>
      {availableRegions.length > 0 && (
        <AiScopeDropdown
          ariaLabel="Filter Country"
          prefix="Country"
          value={selectedRegion || 'All'}
          defaultValue="All"
          icon={<Building2 size={12} />}
          onChange={(value) => onFilterChange('region', value)}
          options={[
            { value: 'All', label: 'All authorized countries' },
            ...availableRegions.map((value) => ({ value, label: value === 'EGY' ? 'Egypt' : value })),
          ]}
        />
      )}
      {availableFunctions.length > 1 && (
        <AiScopeDropdown
          ariaLabel="Filter Department"
          prefix="Dept"
          value={selectedFunction || 'All'}
          defaultValue="All"
          icon={<Building2 size={12} />}
          onChange={(val) => onFilterChange('function', val)}
          options={[
            {
              value: 'All',
              label: 'All authorized departments',
              badge: `${availableFunctions.length} Depts`,
            },
            ...availableFunctions.map((fn) => ({
              value: fn,
              label: fn,
              badge: 'Dept',
            })),
          ]}
        />
      )}

      <AiScopeDropdown
        ariaLabel={selectedFunction ? `Filter ${selectedFunction} Team` : 'Filter Team'}
        prefix="Team"
        value={selectedTeam}
        defaultValue="All"
        icon={<Users size={12} />}
        onChange={(val) => onFilterChange('team', val)}
        options={[
          {
            value: 'All',
            label: selectedFunction ? `All ${selectedFunction} teams` : 'All authorized teams',
            badge: `${availableTeams.length} Teams`,
          },
          ...availableTeams.map((t) => ({
            value: t.value,
            label: t.label,
            badge: t.badge,
          })),
        ]}
      />

      {availablePositions.length > 0 && (
        <AiScopeDropdown
          ariaLabel="Filter Position"
          prefix="Position"
          value={selectedPosition || 'All'}
          defaultValue="All"
          icon={<Users size={12} />}
          onChange={(value) => onFilterChange('position', value)}
          options={[
            { value: 'All', label: 'All positions' },
            ...availablePositions.map((value) => ({ value, label: value })),
          ]}
        />
      )}

      <AiScopeDropdown
        ariaLabel="Filter Branch"
        prefix="Branch"
        value={selectedBranch}
        defaultValue="all"
        icon={<Building2 size={12} />}
        onChange={(val) => onFilterChange('branch', val)}
        options={[
          ...(availableBranches.length !== 1
            ? [
                {
                  value: 'all',
                  label: 'All branches',
                  badge: `${availableBranches.length} Branches`,
                },
              ]
            : []),
          ...availableBranches.map((bk) => ({
            value: bk.toLowerCase(),
            label: bk.charAt(0).toUpperCase() + bk.slice(1),
            badge: bk.toLowerCase() === 'clinics' ? 'Outpatient' : 'Hospital',
          })),
        ]}
      />

      <AiScopeDropdown
        ariaLabel="Filter Performance Level"
        prefix="Level"
        value={selectedLevel}
        defaultValue="All"
        icon={<Layers size={12} />}
        onChange={(val) => onFilterChange('performance_level', val)}
        options={[
          ...(availableLevels.length > 1
            ? [{ value: 'All', label: 'All Levels', badge: 'Full Scope' }]
            : []),
          ...availableLevels.map((lvl) => ({
            value: lvl,
            label: lvl === 'Employee' ? 'Employee' : `${lvl} BSC`,
            badge:
              lvl === 'Employee'
                ? 'Agents'
                : lvl === 'Managerial'
                ? 'Leaders'
                : 'Executive',
          })),
        ]}
      />

      <div
        role="group"
        aria-label="Response detail mode"
        className="inline-flex items-center rounded-full border border-slate-200/90 bg-slate-50/90 p-0.5 text-xs font-bold"
      >
        <button
          type="button"
          aria-pressed={answerDetail === 'brief' || answerDetail === 'auto'}
          onClick={() => onChangeAnswerDetail('brief')}
          className={`rounded-full px-2.5 py-1 transition-colors ${
            answerDetail === 'brief' || answerDetail === 'auto'
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-blue-600'
          }`}
        >
          Brief
        </button>
        <button
          type="button"
          aria-pressed={answerDetail === 'details'}
          onClick={() => onChangeAnswerDetail('details')}
          className={`rounded-full px-2.5 py-1 transition-colors ${
            answerDetail === 'details'
              ? 'bg-blue-600 text-white shadow-2xs'
              : 'text-slate-600 hover:text-blue-600'
          }`}
        >
          Details
        </button>
      </div>
    </div>
  );
}
