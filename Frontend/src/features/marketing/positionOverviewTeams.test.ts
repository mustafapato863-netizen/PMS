import { describe, expect, it } from 'vitest';
import { positionOverviewIdentity } from './positionOverviewTeams';

describe('positionOverviewIdentity', () => {
  it('labels Administration without using the offshore database name', () => {
    expect(positionOverviewIdentity('administration')).toMatchObject({
      label: 'Administration',
      dbName: 'Offshore Admin & Management',
      overviewTitle: 'Administration Overview',
      overviewPath: '/team/administration',
    });
  });

  it('keeps Marketing as the default and uses each department name', () => {
    expect(positionOverviewIdentity()).toMatchObject({ label: 'Marketing', dbName: 'Marketing' });
    expect(positionOverviewIdentity('finance').overviewTitle).toBe('Finance Overview');
    expect(positionOverviewIdentity('human-resources').overviewTitle).toBe('Human Resources Overview');
    expect(positionOverviewIdentity('it')).toMatchObject({ label: 'IT', dbName: 'IT', overviewTitle: 'IT Overview' });
  });
});
