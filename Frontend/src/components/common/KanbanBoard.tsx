import React from 'react';
import { motion } from 'framer-motion';

export interface KanbanColumnProps {
  id: string;
  title: string;
  items: KanbanItemProps[];
}

export interface KanbanItemProps {
  id: string;
  title: string;
  subtitle: string;
  statusColor: string;
}

interface KanbanBoardProps {
  columns: KanbanColumnProps[];
}

const KanbanBoard: React.FC<KanbanBoardProps> = ({ columns }) => {
  return (
    <div className="flex w-full gap-6 overflow-x-auto pb-4 custom-scrollbar">
      {columns.map((col) => (
        <div key={col.id} className="min-w-[300px] flex-1 flex flex-col glass-panel rounded-xl p-4">
          <div className="flex justify-between items-center mb-4 pb-2 border-b border-[var(--border-light)]">
            <h3 className="font-bold text-[var(--text-primary)] uppercase text-xs tracking-wider opacity-90">{col.title}</h3>
            <span className="bg-[var(--bg-sunken)] text-[var(--text-secondary)] px-2.5 py-0.5 rounded-full text-xs font-bold shadow-sm border border-[var(--border-light)]">
              {col.items.length}
            </span>
          </div>
          
          <div className="flex-1 flex flex-col gap-3 min-h-[200px]">
            {col.items.map((item) => (
              <motion.div
                key={item.id}
                layoutId={item.id}
                whileHover={{ y: -2, scale: 1.01 }}
                className="bg-[var(--bg-surface)] rounded-lg p-3 cursor-grab active:cursor-grabbing border-l-4 border-y border-r border-[var(--border-light)] hover:border-[var(--border-medium)] transition-all shadow-sm"
                style={{ borderLeftColor: item.statusColor }}
              >
                <div className="flex justify-between items-start mb-1">
                  <h4 className="font-bold text-[var(--text-primary)] text-sm">{item.title}</h4>
                </div>
                <p className="text-xs text-[var(--text-muted)] font-medium">{item.subtitle}</p>
              </motion.div>
            ))}
            {col.items.length === 0 && (
              <div className="flex-1 flex items-center justify-center border-2 border-dashed border-[var(--border-light)] rounded-lg bg-[var(--bg-sunken)]/30">
                <span className="text-xs text-[var(--text-faint)] font-semibold">Drop items here</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default KanbanBoard;
