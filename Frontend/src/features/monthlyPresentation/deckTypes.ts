import type { GradeClass } from '../../constants/grades';
import type { InsightsWorkspace, InsightKpiDiagnosisRow } from '../insights/types';
import type { DeckAction, DeckStatus, LockedPeriod, Readiness, RegionCode } from './model';

export interface TeamReady { team: string; fn: string; status: Readiness; detail: string; score: number | null; scoreChange: number | null; worstKpi: InsightKpiDiagnosisRow | null }
export interface DeckData {
  code: RegionCode; period: LockedPeriod; previousLabel: string | null; status: DeckStatus;
  ws: InsightsWorkspace | undefined; teams: TeamReady[]; actions: DeckAction[];
  gradeMix: Record<GradeClass, number> | null; gradeMixExcluded: string[];
  owners: Array<{ id: string; name: string; role?: string }>; mask: (name: string | null | undefined) => string;
  /** Masking on: free text is rewritten with aliases from knownNames (or hidden when the list is empty). */
  masked: boolean; knownNames: string[];
}

