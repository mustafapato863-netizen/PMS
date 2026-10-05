import { useNavigate } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import type { PerformanceLevelFilter, TeamSummary } from '../../types';
import { getGradeTone, gradeTokenVar, type GradeClass } from '../../constants/grades';

interface TeamSummaryTableProps {
  teams: TeamSummary[];
  currentMonth: string;
  performanceLevel: PerformanceLevelFilter;
}

const GradeCell = ({ count, total, grade }: { count: number; total: number; grade: GradeClass }) => (
  <td className="px-3 py-3 text-center">
    <div className={`inline-flex flex-col items-center`}>
      <span className="text-sm font-bold" style={{ color: gradeTokenVar(grade, 'text') }}>{count}</span>
      {total > 0 && (
        <span className="text-[10px] text-[var(--text-muted)] font-medium">
          {((count / total) * 100).toFixed(0)}%
        </span>
      )}
    </div>
  </td>
);

const TeamSummaryTable = ({ teams, currentMonth, performanceLevel }: TeamSummaryTableProps) => {
  const navigate = useNavigate();

  const handleTeamClick = (teamId: string) => {
    navigate(`/team/${teamId}?month=${encodeURIComponent(currentMonth)}&performance_level=${encodeURIComponent(performanceLevel)}`);
  };

  const getScoreColor = (score: number) => getGradeTone(score).text;

  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-[var(--border-light)]">
            <th className="px-4 py-3 text-left text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">Team</th>
            <th className="px-3 py-3 text-center text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">Agents</th>
            <th className="px-3 py-3 text-center text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">Avg Score</th>
            <th className="px-3 py-3 text-center text-xs font-bold uppercase tracking-wider" style={{ color: gradeTokenVar('A', 'text') }}>A</th>
            <th className="px-3 py-3 text-center text-xs font-bold uppercase tracking-wider" style={{ color: gradeTokenVar('B', 'text') }}>B</th>
            <th className="px-3 py-3 text-center text-xs font-bold uppercase tracking-wider" style={{ color: gradeTokenVar('C', 'text') }}>C</th>
            <th className="px-3 py-3 text-center text-xs font-bold uppercase tracking-wider" style={{ color: gradeTokenVar('D', 'text') }}>D</th>
            <th className="px-3 py-3 text-center text-xs font-bold uppercase tracking-wider" style={{ color: gradeTokenVar('E', 'text') }}>E</th>
            <th className="px-3 py-3 text-center text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider"></th>
          </tr>
        </thead>
        <tbody>
          {teams.length === 0 ? (
            <tr>
              <td colSpan={9} className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
                No team data available for this month.
              </td>
            </tr>
          ) : (
            teams.map((team, idx) => (
              <tr
                key={team.teamId}
                onClick={() => handleTeamClick(team.teamId)}
                className={`cursor-pointer border-b border-[var(--border-light)] transition-all duration-150 hover:bg-[var(--sidebar-active-bg)] ${
                  idx % 2 === 0 ? 'bg-[var(--bg-surface)]' : 'bg-[var(--bg-sunken)]/20'
                }`}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                    <span className="text-sm font-bold text-blue-600 dark:text-blue-400 hover:underline transition-colors">
                      {team.teamName}
                    </span>
                  </div>
                </td>
                <td className="px-3 py-3 text-center">
                  <span className="text-sm font-bold text-[var(--text-secondary)]">{team.agentCount}</span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span className="text-sm font-extrabold" style={{ color: getScoreColor(team.avgScore) }}>
                    {team.avgScore.toFixed(1)}%
                  </span>
                </td>
                <GradeCell count={team.classA} total={team.agentCount} grade="A" />
                <GradeCell count={team.classB} total={team.agentCount} grade="B" />
                <GradeCell count={team.classC} total={team.agentCount} grade="C" />
                <GradeCell count={team.classD} total={team.agentCount} grade="D" />
                <GradeCell count={team.classE} total={team.agentCount} grade="E" />
                <td className="px-3 py-3 text-center">
                  <ArrowUpRight size={14} className="text-[var(--text-faint)] group-hover:text-blue-500 transition-colors" />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

export default TeamSummaryTable;
