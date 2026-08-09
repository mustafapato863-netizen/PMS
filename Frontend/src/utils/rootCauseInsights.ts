import type { PMSAction } from '../types';

export interface RootCauseSummary {
  total: number;
  byType: Record<string, number>;
  rootCauses: Record<string, number>;
  employeesActioned: number;
  actions: PMSAction[];
}

type RootCausePattern = {
  label: string;
  patterns: RegExp[];
};

const ROOT_CAUSE_PATTERNS: RootCausePattern[] = [
  {
    label: 'Rejection Rate After Re-Submission',
    patterns: [
      /rejection\s+rate\s+after\s+re[-\s]?submission/i,
      /re[-\s]?submission\s+rejection/i,
    ],
  },
  {
    label: 'Initial Rejection Rate',
    patterns: [
      /initial\s+rejection\s+rate/i,
      /rejection\s+rate\s+initial/i,
    ],
  },
  {
    label: 'Initial Error Rate',
    patterns: [
      /initial\s+error\s+rate/i,
      /\binitial\s+error\b/i,
    ],
  },
  {
    label: 'Submission Rate',
    patterns: [
      /submission\s+rate/i,
      /submission\s+within\s+due\s+date/i,
      /submitted\s+within\s+due\s+date/i,
    ],
  },
  {
    label: 'Attendance Rate',
    patterns: [
      /patient\s+attendance\s+rate/i,
      /attendance\s+rate/i,
      /\battendance\b/i,
      /\battend\b/i,
    ],
  },
  {
    label: 'Booking Rate',
    patterns: [
      /booking\s+rate/i,
      /booking\s*cr(?:%| rate)?/i,
      /\bbooking\b/i,
    ],
  },
  {
    label: 'Attended CR',
    patterns: [
      /attended\s*cr(?:%| rate)?/i,
      /\battended\s+cr\b/i,
    ],
  },
  {
    label: 'AHT (Handle Time)',
    patterns: [
      /\baht\b/i,
      /handle\s*time/i,
      /turnaround\s*time/i,
    ],
  },
  {
    label: 'Quality Score',
    patterns: [
      /quality\s+score/i,
      /quality\s+errors\s+rate/i,
      /quality\s+errors/i,
      /\bquality\b/i,
    ],
  },
  {
    label: 'UTZ',
    patterns: [
      /\butz\b/i,
      /utilization/i,
      /utilisation/i,
    ],
  },
  {
    label: 'Abandon Rate',
    patterns: [
      /abandon\s+rate/i,
      /\babandon\b/i,
    ],
  },
  {
    label: 'Rejection Rate',
    patterns: [
      /rejection\s+rate(?!\s+(after|after\s+re[-\s]?submission|initial))/i,
      /\brejection\b(?!\s+(rate|after))/i,
    ],
  },
  {
    label: 'OP Census Ach',
    patterns: [
      /\bop\s*census\b/i,
      /\bopcensus\b/i,
    ],
  },
  {
    label: 'OP Revenue Ach',
    patterns: [
      /\bop\s*revenue\b/i,
      /\boprevenue\b/i,
    ],
  },
  {
    label: 'IP Census Ach',
    patterns: [
      /\bip\s*census\b/i,
      /\bipcensus\b/i,
    ],
  },
  {
    label: 'IP Revenue Ach',
    patterns: [
      /\bip\s*revenue\b/i,
      /\biprevenue\b/i,
    ],
  },
  {
    label: 'Activity Score',
    patterns: [
      /activity\s+score/i,
      /\bactivity\b/i,
    ],
  },
  {
    label: 'Reachability',
    patterns: [
      /reachability/i,
    ],
  },
  {
    label: 'Queries Handled',
    patterns: [
      /queries\s+handled/i,
      /\bqueries\b/i,
    ],
  },
  {
    label: 'Waiting Time',
    patterns: [
      /waiting\s*time/i,
    ],
  },
  {
    label: 'Average Transaction Value',
    patterns: [
      /average\s+transaction\s+value/i,
      /\batv\b/i,
    ],
  },
  {
    label: 'Prescription Contribution',
    patterns: [
      /prescription\s+contribution/i,
      /prescription/i,
    ],
  },
  {
    label: 'Tender Compliance',
    patterns: [
      /tender\s+compliance/i,
    ],
  },
  {
    label: 'Leakage',
    patterns: [
      /\bleakage\b/i,
    ],
  },
];

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}%]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function extractKpiMentions(text: string): string[] {
  if (!text?.trim()) return [];

  const normalized = normalizeText(text);
  const matches: string[] = [];
  const seen = new Set<string>();

  for (const entry of ROOT_CAUSE_PATTERNS) {
    if (seen.has(entry.label)) continue;
    if (entry.patterns.some((pattern) => pattern.test(normalized))) {
      seen.add(entry.label);
      matches.push(entry.label);
    }
  }

  return matches;
}

export function summarizeRootCauses(actions: PMSAction[]): RootCauseSummary {
  const byType = actions.reduce<Record<string, number>>((acc, action) => {
    acc[action.action_type] = (acc[action.action_type] || 0) + 1;
    return acc;
  }, {});

  const rootCauses = actions.reduce<Record<string, number>>((acc, action) => {
    const mentionedKpis = extractKpiMentions(action.root_cause_note || '');
    const uniqueMentions = mentionedKpis.length > 0 ? Array.from(new Set(mentionedKpis)) : ['Other'];

    uniqueMentions.forEach((label) => {
      acc[label] = (acc[label] || 0) + 1;
    });

    return acc;
  }, {});

  return {
    total: actions.length,
    byType,
    rootCauses,
    employeesActioned: new Set(actions.map((action) => action.employee_id)).size,
    actions,
  };
}

export function formatKpiMentions(text: string): string {
  const mentions = extractKpiMentions(text);
  if (mentions.length === 0) return '';
  return Array.from(new Set(mentions)).join(' | ');
}
