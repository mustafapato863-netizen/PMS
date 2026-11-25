import type { PMSAction } from '../../types';
import type { ExecRecord } from './compose';
import { parseTeamCountry, sameCountryBusinessTeam, sameMergedTeam } from '../team/countryTeamIdentity';

export interface ReviewUnit {
  id: string;
  name: string;
  score: number;
  people: number;
  bottleneck?: string;
  region?: string;
  role?: string;
  team?: string;
}

export function sameReviewTeam(left: string, right: string, country: ReturnType<typeof parseTeamCountry>) {
  return (country !== null && sameCountryBusinessTeam(left, right, country)) || sameMergedTeam(left, right);
}

/** Monthly Review historically stores role-wide interventions with this note format. */
export function isSavedRoleIntervention(action: PMSAction) {
  return /^Owner: .*?\. Status: (?:Open|In Progress|Completed)\. Expected impact: /s.test(action.root_cause_note);
}

export function actionMatchesRecord(action: PMSAction, record: ExecRecord) {
  const country = parseTeamCountry(record.region);
  return action.employee_id.trim().toLowerCase() === record.employeeId.trim().toLowerCase()
    && action.team.trim() !== ''
    && sameReviewTeam(action.team, record.team, country)
    && action.month.trim().toLowerCase() === record.period.month.toLowerCase()
    && action.year === record.period.year;
}
