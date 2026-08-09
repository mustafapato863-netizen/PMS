import { Trophy, Clock, UserX } from 'lucide-react';
import type { AgentWithLocation } from '../../hooks/usePerformanceData';
import { parseAHTtoSeconds } from '../../hooks/usePerformanceData';

interface AgentRankingProps {
  agents: AgentWithLocation[];
}

export default function AgentRanking({ agents }: AgentRankingProps) {
  // Sort agents by evaluation score descending
  const sortedAgents = [...agents].sort((a, b) => b.evaluation.score - a.evaluation.score);
  
  const topAgents = sortedAgents.slice(0, 3);
  // Bottom 3 agents (exclude top 3 if there are fewer than 6 agents total)
  const bottomAgents = sortedAgents.slice(Math.max(3, sortedAgents.length - 3)).reverse();

  const AgentRow = ({ agent, isTop }: { agent: AgentWithLocation, isTop: boolean }) => {
    const noShowRate = (1 - agent.actual.attend_rate) * 100;
    
    return (
      <div className="flex items-center justify-between p-3 rounded-xl bg-white border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shadow-inner ${isTop ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
            {agent.identity.name.split(' ').map(n => n[0]).slice(0, 2).join('')}
          </div>
          <div>
            <p className="text-sm font-bold text-slate-800">{agent.identity.name}</p>
            <p className={`text-[10px] font-semibold mt-0.5 ${isTop ? 'text-emerald-600' : 'text-red-500'}`}>
              Score: {agent.evaluation.score.toFixed(1)}%
            </p>
          </div>
        </div>
        
        {/* Context Tags */}
        <div className="flex flex-col items-end gap-1">
          {noShowRate > 30 && (
             <div className="flex items-center gap-1 text-[9px] font-bold bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full border border-amber-100">
               <UserX className="w-3 h-3" />
               High No-Show
             </div>
          )}
          {parseAHTtoSeconds(agent.calls.aht_raw) > 150 && (
            <div className="flex items-center gap-1 text-[9px] font-bold bg-rose-50 text-rose-600 px-2 py-0.5 rounded-full border border-rose-100">
              <Clock className="w-3 h-3" />
              High AHT
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-slate-50/50 rounded-2xl p-6 shadow-inner border border-slate-200/60 h-full flex flex-col">
      <h3 className="text-sm font-extrabold text-slate-800 uppercase tracking-wider mb-5 flex items-center gap-2">
        <Trophy className="w-5 h-5 text-indigo-500" />
        Agent Performance Ranking
      </h3>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
        {/* Top Performers */}
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-emerald-600 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Top 3 Performers
          </h4>
          {topAgents.map(agent => (
            <AgentRow key={agent.identity.name} agent={agent} isTop={true} />
          ))}
        </div>

        {/* Bottom Performers */}
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-red-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500"></span> Bottom 3 (Action Required)
          </h4>
          {bottomAgents.map(agent => (
            <AgentRow key={agent.identity.name} agent={agent} isTop={false} />
          ))}
        </div>
      </div>
    </div>
  );
}
