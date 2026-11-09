import { describe, expect, it } from 'vitest';
import {
  buildRoleDetail,
  hasRoleDetailForSlug,
  recordMatchesRole,
  supportForSlug,
} from './roleDetailData';
import { CALL_CENTER_DEEP_DIVE_SEP_2026 } from './callCenterDeepDiveData';
import type { ExecRecord } from '../executive/compose';

describe('roleDetailData - Support position and role matching', () => {
  const dummyPeriod = { key: '2026-09', year: 2026, month: 'September' };

  const trainerRecord: ExecRecord = {
    employeeId: 'SGHD70117',
    name: 'Hagar Ahmed Amin Diab',
    team: 'Call Center',
    region: 'EGY',
    position: 'Call Center trainer',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 100.0,
    kpis: [],
  };

  const qaRecord: ExecRecord = {
    employeeId: 'SGHD70138',
    name: 'Fahmy Sabry El-Saadany',
    team: 'Call Center',
    region: 'EGY',
    position: 'Quality Assurance',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 84.4,
    kpis: [],
  };

  const inboundTlRecord: ExecRecord = {
    employeeId: 'SGHD70070',
    name: 'Adham Sameh Abdallah Arafa',
    team: 'Call Center',
    region: 'EGY',
    position: 'Inbound Team Leader',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 93.4,
    kpis: [],
  };

  const outboundTlRecord: ExecRecord = {
    employeeId: 'SGHD70072',
    name: 'Amr Badawy Mohamed',
    team: 'Call Center',
    region: 'EGY',
    position: 'Outbound Team Leader',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 86.3,
    kpis: [],
  };

  const wfmRecord: ExecRecord = {
    employeeId: 'SGHD70079',
    name: 'Mohamed Tarek Abdelghafar Soliman',
    team: 'Call Center',
    region: 'EGY',
    position: 'Workforce analyst',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 88.7,
    kpis: [],
  };

  const unrelatedRecord: ExecRecord = {
    employeeId: 'SGHD99999',
    name: 'Unrelated Person',
    team: 'Call Center',
    region: 'EGY',
    position: 'General Staff',
    level: 'Employee',
    branches: [],
    period: dummyPeriod,
    score: 75.0,
    kpis: [],
  };

  it('matches Call Center trainer to trainer role', () => {
    expect(recordMatchesRole(trainerRecord, 'trainer', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
    expect(recordMatchesRole(trainerRecord, 'call-center-trainer', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
  });

  it('matches Quality Assurance to quality-specialist role', () => {
    expect(recordMatchesRole(qaRecord, 'quality-specialist', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
    expect(recordMatchesRole(qaRecord, 'qa', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
  });

  it('matches Team Leader positions to team-leader role', () => {
    expect(recordMatchesRole(inboundTlRecord, 'team-leader', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
    expect(recordMatchesRole(outboundTlRecord, 'team-leader', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
  });

  it('matches Workforce analyst to workforce-planning role', () => {
    expect(recordMatchesRole(wfmRecord, 'workforce-planning', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
    expect(recordMatchesRole(wfmRecord, 'wfm', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(true);
  });

  it('does not match unrelated position to support roles', () => {
    expect(recordMatchesRole(unrelatedRecord, 'trainer', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(false);
    expect(recordMatchesRole(unrelatedRecord, 'quality-specialist', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(false);
    expect(recordMatchesRole(unrelatedRecord, 'team-leader', CALL_CENTER_DEEP_DIVE_SEP_2026)).toBe(false);
  });

  it('resolves support positions through supportForSlug and hasRoleDetailForSlug', () => {
    expect(supportForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'trainer')).toBeDefined();
    expect(supportForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'quality-specialist')).toBeDefined();
    expect(supportForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'team-leader')).toBeDefined();
    expect(supportForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'workforce-planning')).toBeDefined();

    expect(hasRoleDetailForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'trainer', [trainerRecord])).toBe(true);
    expect(hasRoleDetailForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'quality-specialist', [qaRecord])).toBe(true);
    expect(hasRoleDetailForSlug(CALL_CENTER_DEEP_DIVE_SEP_2026, 'unknown-role', [])).toBe(false);
  });

  it('builds role detail with accurate evaluated score and holder name', () => {
    const detail = buildRoleDetail(
      CALL_CENTER_DEEP_DIVE_SEP_2026,
      'trainer',
      [],
      [trainerRecord],
    );

    expect(detail.roleTitle).toBe('Trainer');
    expect(detail.personName).toBe('Hagar Ahmed Amin Diab');
    expect(detail.score).toBe(100.0);
    expect(detail.grade).toBe('A');
    expect(detail.members.length).toBeGreaterThan(0);
    expect(detail.members[0].personName).toBe('Hagar Ahmed Amin Diab');
    expect(detail.members[0].employeeId).toBe('SGHD70117');
  });
});
