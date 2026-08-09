import { describe, expect, it } from 'vitest';
import {
  PRE_APPROVALS_UAE_TEAM,
  PRE_APPROVALS_UAE_TEAM_ID,
  TEAM_DB_NAME_MAP,
  TEAM_ID_MAP,
  TEAM_NAME_MAP,
  isPreApprovalsUaeTeam,
  preApprovalsWorkflowForTeam,
  isRcmTeam,
  isRcmDomainTeam,
  RCM_TEAM,
  RCM_TEAM_ID,
  RCM_DOMAIN_LABELS,
  rcmGroupForTeam,
  isRcmGroupTeam,
  sameCanonicalTeam,
} from '../../types';

describe('Pre-Approvals UAE parent team', () => {
  it('keeps the parent route stable while exposing a concise display name', () => {
    expect(TEAM_ID_MAP[PRE_APPROVALS_UAE_TEAM]).toBe(PRE_APPROVALS_UAE_TEAM_ID);
    expect(TEAM_NAME_MAP[PRE_APPROVALS_UAE_TEAM_ID]).toBe(PRE_APPROVALS_UAE_TEAM);
    expect(TEAM_DB_NAME_MAP[PRE_APPROVALS_UAE_TEAM_ID]).toBe(PRE_APPROVALS_UAE_TEAM);
  });

  it('classifies UAE source teams by workflow without merging IP and OP scores', () => {
    expect(preApprovalsWorkflowForTeam('Pre-Approvals IP Final Dubai')).toBe('ip_final');
    expect(preApprovalsWorkflowForTeam('Pre-Approvals OP Final SHJAJM')).toBe('op_final');
    expect(preApprovalsWorkflowForTeam('Pre-Approvals IP Elective Dubai')).toBe('ip_elective');
    expect(preApprovalsWorkflowForTeam('Pre-Approvals IP Offshore')).toBeNull();
  });

  it('matches the parent to UAE sources but keeps workflow aliases separate', () => {
    expect(isPreApprovalsUaeTeam('Pre-Approvals IP Final Dubai')).toBe(true);
    expect(sameCanonicalTeam('Pre-Approvals', 'Pre-Approvals OP Final')).toBe(true);
    expect(sameCanonicalTeam('Pre-Approvals IP Final', 'Pre-Approvals OP Final')).toBe(false);
    expect(isPreApprovalsUaeTeam('Pre-Approvals IP Offshore')).toBe(false);
  });

  it('groups RCM source teams under one presentation parent without changing child identities', () => {
    expect(TEAM_ID_MAP[RCM_TEAM]).toBe(RCM_TEAM_ID);
    expect(TEAM_NAME_MAP[RCM_TEAM_ID]).toBe(RCM_TEAM);
    expect(TEAM_DB_NAME_MAP[RCM_TEAM_ID]).toBe(RCM_TEAM);
    expect(isRcmTeam('Coding')).toBe(true);
    expect(isRcmTeam('Pre-Approvals IP Offshore')).toBe(true);
    expect(isRcmDomainTeam('Submission', 'submission')).toBe(true);
    expect(isRcmDomainTeam('Coding', 'submission')).toBe(false);
    expect(RCM_DOMAIN_LABELS.pre_approvals).toBe('Pre-Approvals');
    expect(sameCanonicalTeam(RCM_TEAM, 'Re-Submission')).toBe(true);
    expect(sameCanonicalTeam('Coding', 'Submission')).toBe(false);
    expect(rcmGroupForTeam('Pre-Approvals IP Offshore')).toBe('offshore_egy');
    expect(rcmGroupForTeam('Coding', 'UAE')).toBe('uae');
    expect(isRcmGroupTeam('Submission', 'offshore_egy', 'EGY')).toBe(true);
  });
});
