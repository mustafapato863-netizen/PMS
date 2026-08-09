import { useState } from 'react';
import { Shield, ShieldAlert, ShieldCheck, Eye, ChevronDown, Lock, User } from 'lucide-react';
import { useUserRole, type UserRole } from '../../context/RoleContext';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';

const ROLE_DETAILS: Record<UserRole, { label: string; icon: React.ComponentType<{ size?: number; className?: string }>; color: string; bg: string; desc: string }> = {
  Admin: {
    label: 'Admin',
    icon: Shield,
    color: 'text-violet-600 border-violet-200 bg-violet-50',
    bg: 'bg-violet-600',
    desc: 'Full read/write access + config settings',
  },
  Manager: {
    label: 'Manager',
    icon: ShieldCheck,
    color: 'text-emerald-600 border-emerald-200 bg-emerald-50',
    bg: 'bg-emerald-600',
    desc: 'Read/write planning, notes & corrective actions',
  },
  Executive: {
    label: 'Executive',
    icon: ShieldAlert,
    color: 'text-amber-600 border-amber-200 bg-amber-50',
    bg: 'bg-amber-600',
    desc: 'Read-only + performance planning & insights',
  },
  Viewer: {
    label: 'Viewer',
    icon: Eye,
    color: 'text-slate-600 border-slate-200 bg-slate-50',
    bg: 'bg-slate-600',
    desc: 'Read-only access (no planning/insights)',
  },
  Agent: {
    label: 'Agent',
    icon: User,
    color: 'text-blue-600 border-blue-200 bg-blue-50',
    bg: 'bg-blue-600',
    desc: 'Access to the assigned employee profile',
  },
};

const RoleSelector = () => {
  const { role, setRole } = useUserRole();
  const [isOpen, setIsOpen] = useState(false);

  const handleRoleChange = (newRole: UserRole) => {
    setRole(newRole);
    setIsOpen(false);
    // Trigger refresh of performance data which will fetch using the new role header
    refreshPerformanceData();
  };

  const ActiveIcon = ROLE_DETAILS[role].icon;

  return (
    <div className="relative z-40">
      <button
        id="btn-role-selector"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-2 text-xs md:text-sm font-bold rounded-xl border shadow-sm transition-all duration-300 hover:scale-[1.02] active:scale-[0.98] ${ROLE_DETAILS[role].color}`}
      >
        <ActiveIcon size={16} className="shrink-0" />
        <span className="hidden sm:inline">Role: {role}</span>
        <ChevronDown size={14} className={`transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          {/* Overlay to close when clicking outside */}
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          
          <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-xl border border-slate-100 p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="px-3 py-2 border-b border-slate-100 mb-1">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Select Security Role</p>
              <p className="text-xs text-slate-500 font-medium">Demonstrates endpoint permission locking</p>
            </div>

            <div className="px-3 py-2 mb-1 rounded-xl bg-slate-50 border border-slate-100">
              <div className="flex items-center gap-2 text-slate-600">
                <Lock size={12} />
                <p className="text-[10px] font-bold uppercase tracking-wider">Role controls what you can see</p>
              </div>
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                Admin shows user management and upload actions. Manager keeps planning tools. Viewer stays read-only.
              </p>
            </div>
            
            <div className="space-y-1">
              {(Object.keys(ROLE_DETAILS) as UserRole[]).map((r) => {
                const item = ROLE_DETAILS[r];
                const ItemIcon = item.icon;
                const isSelected = r === role;
                
                return (
                  <button
                    key={r}
                    onClick={() => handleRoleChange(r)}
                    className={`w-full flex items-start gap-3 p-2.5 rounded-xl text-left transition-all hover:bg-slate-50 ${
                      isSelected ? 'bg-slate-50 border border-slate-200/50' : 'border border-transparent'
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 ${item.bg}`}>
                      <ItemIcon size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-bold text-slate-800">{item.label}</p>
                        {isSelected && (
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]" />
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 font-medium truncate mt-0.5">{item.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default RoleSelector;
