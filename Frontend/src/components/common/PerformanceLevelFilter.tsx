import CustomDropdown from './CustomDropdown';
import { Users } from 'lucide-react';
import type { PerformanceLevelFilter as Level } from '../../types';

const LEVELS: Level[] = ['All', 'Employee', 'Managerial', 'Corporate'];

interface PerformanceLevelFilterProps {
  value: Level;
  onChange: (level: Level) => void;
  disabled?: boolean;
}

const PerformanceLevelFilter = ({ value, onChange, disabled }: PerformanceLevelFilterProps) => {
  if (disabled) {
    return (
      <div className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] opacity-80">
        <Users className="h-3.5 w-3.5 text-slate-400" />
        <span>{value === 'All' ? 'Employee' : value}</span>
      </div>
    );
  }

  return (
    <CustomDropdown
      value={value}
      options={LEVELS.map((level) => ({ value: level, label: level }))}
      onChange={(val) => onChange(val as Level)}
      icon={<Users className="h-4 w-4 text-slate-400" />}
      ariaLabel="Performance Level"
      size="md"
    />
  );
};

export default PerformanceLevelFilter;
