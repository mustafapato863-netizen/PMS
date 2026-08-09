interface TeamSegmentedControlProps {
  activeTeam: 'inbound' | 'outbound';
  setActiveTeam: (team: 'inbound' | 'outbound') => void;
}

const TeamSegmentedControl = ({
  activeTeam,
  setActiveTeam,
}: TeamSegmentedControlProps) => {
  return (
    <div className="flex justify-center mb-6">
      <div className="bg-[var(--bg-sunken)] backdrop-blur-md p-1 rounded-xl flex gap-1 border border-[var(--border-light)] shadow-inner">
        {(['inbound', 'outbound'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setActiveTeam(t)}
            className={`relative px-6 py-2 rounded-lg text-sm font-bold transition-all duration-250 cursor-pointer ${
              activeTeam === t
                ? 'bg-[var(--bg-surface)] text-blue-600 dark:text-blue-400 shadow-md scale-100'
                : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface)]/40'
            }`}
          >
            {t === 'inbound' ? 'Inbound Team' : 'Outbound Team'}
          </button>
        ))}
      </div>
    </div>
  );
};

export default TeamSegmentedControl;
