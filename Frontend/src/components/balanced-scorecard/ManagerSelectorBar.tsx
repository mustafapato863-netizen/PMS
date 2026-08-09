import { ListFilter } from 'lucide-react';
import type { ManagerSnapshot } from './managerSnapshots';

interface ManagerSelectorBarProps {
  activeManager: ManagerSnapshot | null;
  managers: ManagerSnapshot[];
  teamName: string | null;
  rosterOpen: boolean;
  onSelectManager: (employeeId: string) => void;
  onToggleRoster: () => void;
}

function initials(name: string) {
  return name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

import CustomDropdown from '../common/CustomDropdown';

export function ManagerSelectorBar({
  activeManager,
  managers,
  teamName,
  rosterOpen,
  onSelectManager,
  onToggleRoster,
}: ManagerSelectorBarProps) {
  if (!activeManager) return null;

  return (
    <section className="bsc-manager-selector" aria-label="Active manager selection">
      <div className="bsc-manager-selector-profile">
        <span className="bsc-manager-selector-avatar" aria-hidden="true">
          {initials(activeManager.employeeName)}
        </span>
        <div className="bsc-manager-selector-copy">
          <span className="bsc-manager-selector-eyebrow">Active manager</span>
          <strong>{activeManager.employeeName}</strong>
          <span className="bsc-manager-selector-role">{activeManager.role || activeManager.teamName || teamName || 'Management'}</span>
          <small>#{activeManager.employeeId}{teamName ? ` · ${teamName}` : ''}</small>
        </div>
      </div>

      <div className="bsc-manager-selector-actions">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-[var(--bsc-panel-muted)] uppercase tracking-wider">Switch manager</span>
          <CustomDropdown
            value={activeManager.employeeId}
            options={managers.map((manager) => ({
              value: manager.employeeId,
              label: `${manager.employeeName} — ${manager.role || manager.teamName || teamName || 'Management'}`,
            }))}
            onChange={(val) => onSelectManager(String(val))}
            ariaLabel="Switch manager"
            size="sm"
          />
        </div>

        <button
          type="button"
          className={`bsc-manager-roster-toggle ${rosterOpen ? 'is-active' : ''}`}
          onClick={onToggleRoster}
          aria-expanded={rosterOpen}
          aria-controls="management-roster-panel"
        >
          <ListFilter size={15} aria-hidden="true" />
          {rosterOpen ? 'Hide roster' : `View all (${managers.length})`}
        </button>
      </div>
    </section>
  );
}

export default ManagerSelectorBar;
