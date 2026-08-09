import React, { useState } from 'react';
import { Plus, User, Calendar, CheckSquare, MessageSquare, Paperclip, Check } from 'lucide-react';
import type { ActionItem } from '../../types';

interface CorrectiveActionWorkspaceProps {
  employeeId: string;
  existingActions: ActionItem[];
}

const CorrectiveActionWorkspace: React.FC<CorrectiveActionWorkspaceProps> = ({ existingActions }) => {
  const [isCreating, setIsCreating] = useState(false);

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <h3 className="heading-3">Action Workspace</h3>
        <button 
          onClick={() => setIsCreating(!isCreating)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm"
        >
          {isCreating ? 'Cancel' : <><Plus size={16} /> New Action</>}
        </button>
      </div>

      {isCreating && (
        <div className="glass-card bg-white p-5 mb-6 border-l-4 border-l-blue-500 shadow-sm">
          <h4 className="text-sm font-bold text-slate-800 mb-4">Create Corrective Action</h4>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-500 mb-1">Action Title</label>
              <input type="text" className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 font-medium focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" placeholder="e.g., Complete Advanced Training" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1">Assign Owner</label>
                <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-md px-3 py-2 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all">
                  <User size={14} className="text-slate-400" />
                  <input type="text" className="bg-transparent border-none text-sm text-slate-800 font-medium focus:outline-none w-full" placeholder="Manager Name" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1">Due Date</label>
                <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-md px-3 py-2 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all">
                  <Calendar size={14} className="text-slate-400" />
                  <input type="date" className="bg-transparent border-none text-sm text-slate-800 font-medium focus:outline-none w-full" />
                </div>
              </div>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 mb-1">Manager Notes</label>
              <textarea className="w-full bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 font-medium focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all min-h-[80px]" placeholder="Add specific expectations..."></textarea>
            </div>
            <div className="flex justify-end pt-2">
              <button className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm" onClick={() => setIsCreating(false)}>
                Save Action
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-4">
        {existingActions.map(action => (
          <div key={action.id} className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm flex flex-col gap-3 transition-shadow hover:shadow-md">
            <div className="flex justify-between items-start">
              <div>
                <h4 className="text-slate-800 font-bold text-sm mb-1">{action.title}</h4>
                <div className="flex items-center gap-4 text-xs text-slate-500 font-medium">
                  <span className="flex items-center gap-1"><User size={12} /> {action.owner}</span>
                  <span className="flex items-center gap-1"><Calendar size={12} /> {action.dueDate}</span>
                </div>
              </div>
              <span className={`px-2 py-1 rounded-full text-[10px] uppercase tracking-wider font-bold ${
                action.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' :
                action.status === 'In Progress' ? 'bg-blue-100 text-blue-700' :
                'bg-slate-100 text-slate-600'
              }`}>
                {action.status}
              </span>
            </div>
            
            {action.notes && (
              <div className="bg-slate-50 border border-slate-100 p-3 rounded-lg flex items-start gap-2">
                <MessageSquare size={14} className="text-slate-400 mt-0.5 shrink-0" />
                <p className="text-xs text-slate-600 italic font-medium">{action.notes}</p>
              </div>
            )}

            <div className="flex items-center gap-3 pt-2 border-t border-slate-100 mt-1">
              <button className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors">
                <Paperclip size={14} /> Upload Evidence
              </button>
              {action.status !== 'Completed' && (
                <button className="flex items-center gap-1.5 text-xs font-bold text-emerald-600 hover:text-emerald-700 ml-auto transition-colors">
                  <Check size={14} /> Mark Completed
                </button>
              )}
            </div>
          </div>
        ))}

        {existingActions.length === 0 && !isCreating && (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 p-8 text-center border-2 border-dashed border-slate-200 rounded-xl bg-slate-50/50">
            <CheckSquare size={32} className="mb-3 opacity-60 text-slate-300" />
            <p className="text-sm font-semibold">No corrective actions currently assigned.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default CorrectiveActionWorkspace;
