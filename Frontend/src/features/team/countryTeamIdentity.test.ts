import { describe, expect, it } from 'vitest';
import {
  businessTeamName,
  countryForSharedRoute,
  countryForStoredTeam,
  distinctCatalogTeams,
  legacySharedTeamRedirect,
  presentationTeamName,
  recordMatchesCatalogTeam,
  sameCountryBusinessTeam,
  sidebarTeamLabel,
  sourceNamesFor,
} from './countryTeamIdentity';

describe('country team identity', () => {
  it('uses one business name and keeps the stored country on the source name', () => {
    expect(businessTeamName('Coding EGY')).toBe('Coding');
    expect(businessTeamName('Submission EGY')).toBe('Submission');
    expect(businessTeamName('Resubmission')).toBe('Re-Submission');
    expect(businessTeamName('Re-Submission EGY')).toBe('Re-Submission');
    expect(countryForStoredTeam('Coding EGY')).toBe('EGY');
    expect(countryForStoredTeam('Coding')).toBe('UAE');
    expect(countryForStoredTeam('Submission')).toBe('UAE');
    expect(sourceNamesFor('coding', 'EGY')).toEqual(['Coding EGY']);
    expect(sourceNamesFor('Coding', 'UAE')).toEqual(['Coding']);
    expect(sourceNamesFor('re-submission', 'EGY')).toEqual(['Resubmission', 'Re-Submission EGY']);
  });

  it('matches aliases only inside the selected country', () => {
    expect(sameCountryBusinessTeam('Coding EGY', 'coding', 'EGY')).toBe(true);
    expect(sameCountryBusinessTeam('Coding EGY', 'Coding', 'UAE')).toBe(false);
    expect(sameCountryBusinessTeam('Resubmission', 'Re-Submission EGY', 'EGY')).toBe(true);
    expect(sameCountryBusinessTeam('Resubmission', 'Re-Submission', 'UAE')).toBe(false);
    expect(sameCountryBusinessTeam('Re-Submission', 're-submission', 'UAE')).toBe(true);
  });

  it('keeps Pre-Approvals IP and Pre-Approvals IP Offshore separate', () => {
    expect(businessTeamName('Pre-Approvals IP')).toBe('Pre-Approvals IP');
    expect(businessTeamName('Pre-Approvals IP Offshore')).toBe('Pre-Approvals IP Offshore');
    expect(countryForStoredTeam('Pre-Approvals IP')).toBeNull();
    expect(sameCountryBusinessTeam('Pre-Approvals IP', 'Pre-Approvals IP Offshore', 'EGY')).toBe(false);
    expect(legacySharedTeamRedirect('pre-approvals-ip')).toBeNull();
  });

  it('sends legacy country URLs to the shared route and leaves /team/coding as UAE', () => {
    expect(legacySharedTeamRedirect('coding-egy')).toEqual({ routeId: 'coding', region: 'EGY' });
    expect(legacySharedTeamRedirect('submission-egy')).toEqual({ routeId: 'submission', region: 'EGY' });
    expect(legacySharedTeamRedirect('resubmission')).toEqual({ routeId: 're-submission', region: 'EGY' });
    expect(countryForSharedRoute('coding', null, null)).toBe('UAE');
    expect(countryForSharedRoute('coding', 'egy', null)).toBe('EGY');
    expect(countryForSharedRoute('coding', 'egy', 'UAE')).toBe('UAE');
    expect(countryForSharedRoute('inbound', 'egy', null)).toBeNull();
  });

  it('does not call a team missing when either Egypt alias has a record at that level', () => {
    expect(recordMatchesCatalogTeam({
      recordTeam: 'Resubmission',
      recordRegion: 'EGY',
      recordLevel: 'Employee',
      catalogTeam: 'Re-Submission EGY',
      catalogRegion: 'EGY',
      levels: ['Employee'],
    })).toBe(true);
    expect(recordMatchesCatalogTeam({
      recordTeam: 'Coding',
      recordRegion: 'UAE',
      recordLevel: 'Employee',
      catalogTeam: 'Coding EGY',
      catalogRegion: 'EGY',
      levels: ['Employee'],
    })).toBe(false);
    expect(recordMatchesCatalogTeam({
      recordTeam: 'Pre-Approvals IP',
      recordRegion: 'EGY',
      catalogTeam: 'Pre-Approvals IP Offshore',
      catalogRegion: 'EGY',
    })).toBe(false);
  });

  it('collapses alias notices inside one country and keeps the other country and distinct teams', () => {
    const teams = distinctCatalogTeams([
      { team: 'Resubmission', performance_levels: ['Employee'] },
      { team: 'Re-Submission EGY', performance_levels: ['Employee'] },
      { team: 'Pre-Approvals IP', performance_levels: ['Employee'] },
      { team: 'Pre-Approvals IP Offshore', performance_levels: ['Employee'] },
    ], 'EGY');
    expect(teams.map((team) => team.team)).toEqual([
      'Resubmission',
      'Pre-Approvals IP',
      'Pre-Approvals IP Offshore',
    ]);
    expect(presentationTeamName('Coding EGY')).toBe('Coding');
    expect(presentationTeamName('Coding EGY', 'EGY')).toBe('Coding');
    expect(sidebarTeamLabel('Coding EGY', ['Coding', 'Coding EGY'])).toBe('Coding · Egypt');
    expect(sidebarTeamLabel('Coding EGY', ['Coding EGY'])).toBe('Coding');
  });
});
