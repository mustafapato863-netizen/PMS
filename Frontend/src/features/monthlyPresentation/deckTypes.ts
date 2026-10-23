import type { GradeClass } from '../../constants/grades';
import type { InsightsWorkspace, InsightKpiDiagnosisRow } from '../insights/types';
import type { ExecutiveSummary } from '../executive/types';
import type { DeckAction, DeckStatus, LockedPeriod, Readiness, RegionCode } from './model';

export interface TeamReady { team: string; fn: string; status: Readiness; detail: string; score: number | null; scoreChange: number | null; worstKpi: InsightKpiDiagnosisRow | null }
export interface DeckData {
  code: RegionCode; period: LockedPeriod; previousLabel: string | null; status: DeckStatus;
  ws: InsightsWorkspace | undefined; teams: TeamReady[]; actions: DeckAction[];
  gradeMix: Record<GradeClass, number> | null; gradeMixExcluded: string[];
  owners: Array<{ id: string; name: string; role?: string }>; mask: (name: string | null | undefined) => string;
  /** Masking on: structured names use aliases; action text and owner notes are never printed. */
  masked: boolean;
  summary?: ExecutiveSummary | null;
}


/** Per-slide data state: a slide renders as soon as its own requests are in, and fails on its own. */
export type SlideState = { status: 'ready' } | { status: 'loading' } | { status: 'error'; message: string; retry?: () => void };
