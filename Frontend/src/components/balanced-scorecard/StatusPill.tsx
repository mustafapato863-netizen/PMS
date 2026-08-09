import { statusClass, statusLabel } from './types';

interface StatusPillProps {
  status?: string;
}

export function StatusPill({ status }: StatusPillProps) {
  const cls = statusClass(status);
  return (
    <span className={`bsc-status-pill ${cls}`}>
      <span className="dot"/>
      {statusLabel(status)}
    </span>
  );
}

export default StatusPill;
