import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Edit2, Play, CheckCircle } from 'lucide-react';
import type { EmployeeCRMRecord, EmployeeStatus } from '../../types';

interface EmployeeTableProps {
  data: EmployeeCRMRecord[];
  onActionClick?: (employeeId: string, actionType: string) => void;
}

const getStatusClass = (status: EmployeeStatus) => {
  switch (status) {
    case 'SIP': return 'status-sip';
    case 'PI': return 'status-pi';
    case 'Average': return 'status-average';
    case 'Meet': return 'status-meet';
    case 'Exceeds': return 'status-exceeds';
    default: return 'status-average';
  }
};

const EmployeeTable: React.FC<EmployeeTableProps> = ({ data, onActionClick }) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="w-full overflow-x-auto glass-panel rounded-xl shadow-sm">
      <table className="crm-table w-full">
        <thead>
          <tr>
            <th></th>
            <th>Employee</th>
            <th>Team</th>
            <th>Score</th>
            <th>Grade</th>
            <th>Trend</th>
            <th>Status</th>
            <th>Root Cause</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {data.map((emp) => (
            <React.Fragment key={emp.id}>
              <tr
                className={`cursor-pointer transition-colors duration-200 ${expandedId === emp.id ? 'bg-slate-100/80' : 'hover:bg-slate-50'}`}
                onClick={() => toggleExpand(emp.id)}
              >
                <td className="w-10 text-center text-slate-400">
                  {expandedId === emp.id ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </td>
                <td className="font-bold text-slate-800">{emp.name}</td>
                <td className="text-slate-600 font-medium">{emp.team}</td>
                <td className="font-bold text-slate-700">{emp.score.toFixed(1)}%</td>
                <td className="font-bold text-slate-700">{emp.grade}</td>
                <td>
                  <span className={`flex items-center gap-1 font-bold ${emp.trend === 'Up' ? 'text-emerald-600' : emp.trend === 'Down' ? 'text-red-600' : 'text-slate-500'}`}>
                    {emp.trend === 'Up' ? '↑' : emp.trend === 'Down' ? '↓' : '→'} {emp.trend}
                  </span>
                </td>
                <td>
                  <span className={`status-badge ${getStatusClass(emp.status)}`}>
                    {emp.status}
                  </span>
                </td>
                <td className="text-slate-600 font-medium truncate max-w-[150px]" title={emp.rootCause}>
                  {emp.rootCause}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onActionClick?.(emp.id, 'edit')}
                      aria-label="Edit Plan"
                      className="p-1.5 hover:bg-slate-200 rounded-md text-slate-400 hover:text-slate-800 transition-colors"
                      title="Edit Plan"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => onActionClick?.(emp.id, 'action')}
                      aria-label="Assign Corrective Action"
                      className="p-1.5 hover:bg-blue-100 rounded-md text-slate-400 hover:text-blue-600 transition-colors"
                      title="Assign Corrective Action"
                    >
                      <Play size={16} />
                    </button>
                  </div>
                </td>
              </tr>
              <AnimatePresence>
                {expandedId === emp.id && (
                  <motion.tr
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <td colSpan={9} className="p-0 border-b border-slate-200">
                      <div className="p-4 bg-slate-50 flex flex-col gap-4 shadow-inner">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
                            <h4 className="text-xs text-slate-500 uppercase font-bold mb-2 flex items-center gap-2">
                              <span className="text-blue-500">📋</span> Suggested Action
                            </h4>
                            <p className="text-sm text-slate-700 leading-relaxed font-medium">
                              {emp.aiSuggestion}
                            </p>
                          </div>

                          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
                            <h4 className="text-xs text-slate-500 uppercase font-bold mb-2">Manager Notes</h4>
                            <p className="text-sm text-slate-600 italic font-medium">
                              "{emp.managerNotes}"
                            </p>
                          </div>

                          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm border-l-4 border-l-blue-500">
                            <h4 className="text-xs text-slate-500 uppercase font-bold mb-2">Active Corrective Action</h4>
                            {emp.correctiveAction ? (
                              <div className="flex items-start gap-2">
                                <CheckCircle size={16} className="text-emerald-500 mt-0.5" />
                                <span className="text-sm font-bold text-slate-800">{emp.correctiveAction}</span>
                              </div>
                            ) : (
                              <span className="text-sm text-slate-500 font-medium">No active plans.</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                  </motion.tr>
                )}
              </AnimatePresence>
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default EmployeeTable;
