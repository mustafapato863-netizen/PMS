import { describe, expect, it } from 'vitest';
import {
  CALL_CENTER_TEAM,
  CALL_CENTER_TEAM_ID,
  TEAM_DB_NAME_MAP,
  TEAM_ID_MAP,
  TEAM_NAME_MAP,
  callCenterChannelForTeam,
  isCallCenterTeam,
  sameCanonicalTeam,
} from '../../types';

describe('Call Center parent team', () => {
  it('maps the parent route and keeps the source channels addressable', () => {
    expect(TEAM_ID_MAP[CALL_CENTER_TEAM]).toBe(CALL_CENTER_TEAM_ID);
    expect(TEAM_NAME_MAP[CALL_CENTER_TEAM_ID]).toBe(CALL_CENTER_TEAM);
    expect(TEAM_DB_NAME_MAP[CALL_CENTER_TEAM_ID]).toBe(CALL_CENTER_TEAM);
  });

  it('classifies only the Egypt call-center channels', () => {
    expect(isCallCenterTeam(CALL_CENTER_TEAM)).toBe(true);
    expect(isCallCenterTeam('Inbound')).toBe(true);
    expect(isCallCenterTeam('Outbound')).toBe(true);
    expect(isCallCenterTeam('Inbound UAE')).toBe(false);
    expect(callCenterChannelForTeam('Inbound')).toBe('inbound');
    expect(callCenterChannelForTeam('Outbound')).toBe('outbound');
  });

  it('treats parent and channels as one scope without pooling channel identities', () => {
    expect(sameCanonicalTeam(CALL_CENTER_TEAM, 'Inbound')).toBe(true);
    expect(sameCanonicalTeam(CALL_CENTER_TEAM, 'Outbound')).toBe(true);
    expect(sameCanonicalTeam('Inbound', 'Outbound')).toBe(false);
  });
});
