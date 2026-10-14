import { describe, expect, it } from 'vitest';
import { resolveTeamRouteId, teamPath } from '../../types';
import { parentTeamView, teamBreadcrumbs } from './functions';

describe('resolveTeamRouteId', () => {
  it('keeps the legacy ids and the slugs of display and DB names working', () => {
    expect(resolveTeamRouteId('pre-approvals')).toBe('pre-approvals');
    expect(resolveTeamRouteId('pre-approvals-ip-offshore')).toBe('pre-approvals');
    expect(resolveTeamRouteId('PRE-APPROVALS-IP-OFFSHORE')).toBe('pre-approvals');
    expect(resolveTeamRouteId('pre-approvals-ip-final-shjajm')).toBe('pre-approvals-ip-final-shj-ajm');
    expect(resolveTeamRouteId('pre-approvals-ip-elective')).toBe('pre-approvals-ip-elective-dubai');
    expect(resolveTeamRouteId('pre-approvals-uae')).toBe('pre-approvals-uae');
  });

  it('returns null for unknown ids, empty input and object-prototype names', () => {
    expect(resolveTeamRouteId('pre-approvals-ip-offshor')).toBeNull();
    expect(resolveTeamRouteId('randd-team')).toBeNull();
    expect(resolveTeamRouteId('constructor')).toBeNull();
    expect(resolveTeamRouteId('')).toBeNull();
    expect(resolveTeamRouteId(undefined)).toBeNull();
  });
});

describe('teamPath', () => {
  it('builds the canonical route id for a known team, and merged views for source teams', () => {
    expect(teamPath('Pre-Approvals IP Offshore')).toBe('/team/pre-approvals');
    expect(teamPath('Pre-Approvals')).toBe('/team/pre-approvals-uae');
    expect(teamPath('Pre-Approvals OP Dubai')).toBe('/team/pre-approvals-op-final');
    expect(teamPath('Pre-Approvals IP Final SHJAJM')).toBe('/team/pre-approvals-ip-final');
    expect(teamPath('Pre-Approvals IP Elective')).toBe('/team/pre-approvals-ip-elective-dubai');
    expect(teamPath('Coding')).toBe('/team/coding');
  });

  it('slugs only an unknown team', () => {
    expect(teamPath('R&D Team')).toBe('/team/randd-team');
  });
});

describe('parentTeamView', () => {
  it('puts the UAE Pre-Approvals workflows, Inbound/Outbound and the other RCM teams under their parent view', () => {
    expect(parentTeamView('Pre-Approvals OP Final SHJAJM')).toBe('Pre-Approvals');
    expect(parentTeamView('Pre-Approvals IP Elective Dubai')).toBe('Pre-Approvals');
    expect(parentTeamView('Inbound')).toBe('Call Center');
    expect(parentTeamView('Coding')).toBe('RCM');
  });

  it('gives parent views and stand-alone teams no parent', () => {
    expect(parentTeamView('Pre-Approvals')).toBeNull();
    expect(parentTeamView('Call Center')).toBeNull();
    expect(parentTeamView('RCM')).toBeNull();
    expect(parentTeamView('Sales')).toBeNull();
    expect(parentTeamView('Inbound UAE')).toBeNull();
  });
});

describe('teamBreadcrumbs', () => {
  const options = { canOpenFunctionSummary: true, allTeamsHref: '/team/all' };

  it('shows Executive Summary > Function > Parent view > Sub-team for a UAE workflow on the Pre-Approvals page', () => {
    expect(teamBreadcrumbs({ ...options, team: 'Pre-Approvals OP Final', displayName: 'Pre-Approvals OP Final' })).toEqual([
      { label: 'Executive Summary', href: '/executive', icon: 'home' },
      { label: 'RCM', href: '/function-summary/rcm' },
      { label: 'Pre-Approvals', href: '/team/pre-approvals-uae' },
      { label: 'Pre-Approvals OP Final', icon: 'team' },
    ]);
  });

  it('shows Function > Sub-team for Pre-Approvals IP Offshore, which the Pre-Approvals page does not show', () => {
    expect(teamBreadcrumbs({ ...options, team: 'Pre-Approvals IP Offshore', displayName: 'Pre-Approvals IP Offshore' })).toEqual([
      { label: 'Executive Summary', href: '/executive', icon: 'home' },
      { label: 'RCM', href: '/function-summary/rcm' },
      { label: 'Pre-Approvals IP Offshore', icon: 'team' },
    ]);
  });

  it('shows Function > Team for a stand-alone team', () => {
    expect(teamBreadcrumbs({ ...options, team: 'Coding', displayName: 'Coding' })).toEqual([
      { label: 'Executive Summary', href: '/executive', icon: 'home' },
      { label: 'RCM', href: '/function-summary/rcm' },
      { label: 'Coding', icon: 'team' },
    ]);
  });

  it('does not repeat the function when the parent view has the same name (Inbound under Call Center)', () => {
    expect(teamBreadcrumbs({ ...options, team: 'Inbound', displayName: 'Inbound' })).toEqual([
      { label: 'Executive Summary', href: '/executive', icon: 'home' },
      { label: 'Call Center', href: '/function-summary/call-center' },
      { label: 'Inbound', icon: 'team' },
    ]);
  });

  it('opens the Executive Summary filtered to the function for roles without the Function Summary', () => {
    expect(teamBreadcrumbs({ ...options, canOpenFunctionSummary: false, team: 'Coding', displayName: 'Coding' })[1])
      .toEqual({ label: 'RCM', href: '/executive?function=RCM' });
  });

  it('shows the all-teams view under Team Performance', () => {
    expect(teamBreadcrumbs({ ...options, team: null, displayName: 'All Teams' })).toEqual([
      { label: 'Executive Summary', href: '/executive', icon: 'home' },
      { label: 'Team Performance', href: '/team/all', icon: 'teams' },
    ]);
  });
});
