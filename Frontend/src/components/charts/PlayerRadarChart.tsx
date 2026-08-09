import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend, Tooltip } from 'recharts';

export interface RadarDataPoint {
  subject: string;
  A: number; // Employee score (e.g., 0-150)
  B?: number; // Benchmark score
  fullMark: number;
}

interface TooltipEntry {
  name?: string;
  value?: number;
  color?: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}

interface PlayerRadarChartProps {
  data: RadarDataPoint[];
  employeeName: string;
  benchmarkName?: string;
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[var(--bg-surface)] border border-[var(--border-medium)] rounded-xl px-3 py-2 shadow-lg text-sm">
        <div className="text-xs text-[var(--text-secondary)] font-semibold mb-1">{label}</div>
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-[var(--text-primary)] font-medium">
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : '0.0'}%
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

const PlayerRadarChart: React.FC<PlayerRadarChartProps> = ({ data, employeeName, benchmarkName }) => {
  if (!data || data.length === 0) return null;

  return (
    <div className="w-full h-[320px]">
      <ResponsiveContainer width="100%" height={320} minWidth={0}>
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="var(--border-light)" />
          <PolarAngleAxis 
            dataKey="subject" 
            tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontWeight: 500 }} 
          />
          <PolarRadiusAxis 
            angle={30} 
            domain={[0, Math.max(100, ...data.map(d => Math.max(d.A || 0, d.B || 0)))]} 
            tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend 
            wrapperStyle={{ fontSize: 12, paddingTop: '10px' }}
            iconType="circle"
          />
          
          {/* Employee Polygon */}
          <Radar 
            name={employeeName} 
            dataKey="A" 
            stroke="var(--color-meet)" 
            fill="var(--color-meet)" 
            fillOpacity={0.4} 
            strokeWidth={2}
          />
          
          {/* Benchmark Polygon (if available) */}
          {benchmarkName && data.some(d => d.B !== undefined) && (
            <Radar 
              name={benchmarkName} 
              dataKey="B" 
              stroke="#8b5cf6" 
              fill="#8b5cf6" 
              fillOpacity={0.2}
              strokeDasharray="4 4"
              strokeWidth={2}
            />
          )}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PlayerRadarChart;
