import { describe, expect, it } from 'vitest';
import { validateTeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord } from '../../types';
import { buildTeamKpiAnalysis, buildTeamKpiRecommendation, formatTeamKpiValue } from './teamKpiAnalysis';

const record = (month: string, booking: number, contribution: number): AgentRecord => ({
  year: 2026,
  identity: { name: 'Agent One', employee_id: 'E1', team: 'Inbound', month },
  calls: { inbound: 100, outbound: 0, total_handled: 100, abandoned: 1, aht_raw: '00:02:30' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: { booking_rate: booking, attend_rate: .7, abandon_rate: .01 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: .8, grade: 'B' },
  kpi_values: [{
    kpi_key: 'booking_rate', label: 'Booking Rate', unit: '%', direction: 'higher_better',
    actual_value: booking, target_value: .65, achievement_ratio: booking / .65,
    weight_applied: .1, contribution,
  }],
});

describe('team KPI analysis', () => {
  it('uses the configured pooled ratio for current, previous and historical baseline periods', () => {
    const currentOne = record('June', .5, .08);
    const currentTwo = record('June', .9, .08);
    const previous = record('May', .25, .08);
    const april = record('April', .5, .08);
    currentTwo.identity.employee_id = 'E2';
    currentOne.raw_data = { numerator: '1', denominator: '2' };
    currentTwo.raw_data = { numerator: '9', denominator: '10' };
    previous.raw_data = { numerator: '1', denominator: '4' };
    april.raw_data = { numerator: '2', denominator: '4' };
    const teamConfig = validateTeamConfig({
      team: 'Inbound',
      db_name: 'Inbound',
      region: 'EGY',
      employee_id_col: 'EmployeeID',
      employee_name_col: 'EmployeeName',
      grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
      kpis: [{
        key: 'Booking', label: 'Booking Rate', weight: 1,
        direction: 'higher_better', unit: '%', color: '#10B981',
        actual_col: 'Actual', target_col: 'Target',
        aggregation: { method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' },
      }],
    });

    const [booking] = buildTeamKpiAnalysis(
      [currentOne, currentTwo],
      [previous],
      { teamConfig, baselineRecords: [april, previous, currentOne, currentTwo] },
    );

    expect(booking.actual).toBeCloseTo(10 / 12);
    expect(booking.previousActual).toBeCloseTo(1 / 4);
    expect(booking.baselineActual).toBeCloseTo(10 / 12);
    expect(booking.previousBaselineActual).toBeCloseTo(1 / 2);
    expect(booking.isNewBaseline).toBe(true);
  });

  it('derives movement, target gap and weighted score gap from real KPI values', () => {
    const current = record('June', .614, .08);
    const previous = record('May', .7, .1);
    const april = record('April', .68, .09);
    const [booking] = buildTeamKpiAnalysis([current], [previous], { baselineRecords: [april, previous, current] });

    expect(booking.actual).toBeCloseTo(.614);
    expect(booking.target).toBeCloseTo(.65);
    expect(booking.movementPercent).toBeCloseTo(-12.29, 1);
    expect(booking.gapPoints).toBeCloseTo(2);
    expect(booking.severity).toBe('attention');
    expect(booking.baselineActual).toBeCloseTo(.7);
    expect(booking.baselineMonth).toBe('May');
    expect(booking.previousBaselineActual).toBeCloseTo(.7);
    expect(booking.previousBaselineMonth).toBe('May');
    expect(booking.isNewBaseline).toBe(false);
    expect(buildTeamKpiRecommendation(booking)).toBe('Improve Booking Rate');
    expect(formatTeamKpiValue(booking.actual, booking.unit)).toBe('61.4%');
  });

  it('treats lower-better KPI decreases as positive movement', () => {
    const current = record('June', .6, .08);
    const previous = record('May', .6, .08);
    current.kpi_values![0] = { ...current.kpi_values![0], kpi_key: 'aht', label: 'AHT', unit: 'min', direction: 'lower_better', actual_value: 2.4, target_value: 2.5 };
    previous.kpi_values![0] = { ...previous.kpi_values![0], kpi_key: 'aht', label: 'AHT', unit: 'min', direction: 'lower_better', actual_value: 2.8, target_value: 2.5 };

    const [aht] = buildTeamKpiAnalysis([current], [previous]);
    expect(aht.targetMet).toBe(true);
    expect(aht.movementPositive).toBe(true);
  });

  it('does not classify near-target achievement as critical when weighted impact is unavailable', () => {
    const current = record('June', .58, .08);
    const previous = record('May', .577, .08);
    current.kpi_values = undefined;
    previous.kpi_values = undefined;
    current.raw_data = { 'T.Booking': '65' };
    previous.raw_data = { 'T.Booking': '65' };

    const booking = buildTeamKpiAnalysis([current], [previous]).find((kpi) => kpi.label === 'Booking Rate')!;
    expect(booking.achievement).toBeCloseTo(89.23, 1);
    expect(booking.severity).toBe('attention');
  });

  it('calculates No Show Rate from missed bookings with a 20% maximum target', () => {
    const currentOne = record('June', .5, .08);
    const currentTwo = record('June', .5, .08);
    const previous = record('May', .5, .08);
    currentOne.kpi_values = undefined;
    currentTwo.kpi_values = undefined;
    previous.kpi_values = undefined;
    currentTwo.identity.employee_id = 'E2';
    currentOne.geo = { bookings: { dubai: 10, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 9, sharjah: 0, ajman: 0, clinics: 0 } };
    currentTwo.geo = { bookings: { dubai: 10, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 1, sharjah: 0, ajman: 0, clinics: 0 } };
    previous.geo = { bookings: { dubai: 20, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 8, sharjah: 0, ajman: 0, clinics: 0 } };

    const analysis = buildTeamKpiAnalysis(
      [currentOne, currentTwo],
      [previous],
      { includeNoShow: true, location: 'dubai' },
    );
    const noShow = analysis.find((kpi) => kpi.label === 'No Show Rate')!;

    expect(noShow.actual).toBeCloseTo(.5);
    expect(noShow.previousActual).toBeCloseTo(.6);
    expect(noShow.target).toBe(.2);
    expect(noShow.lowerBetter).toBe(true);
    expect(noShow.movementPositive).toBe(true);
    expect(noShow.achievement).toBeCloseTo(40);
  });

  it('adds call-weighted AHT analysis when Outbound supplies an AHT target', () => {
    const currentOne = record('June', .5, .08);
    const currentTwo = record('June', .5, .08);
    const previous = record('May', .5, .08);
    currentOne.identity.team = 'Outbound';
    currentTwo.identity.team = 'Outbound';
    previous.identity.team = 'Outbound';
    currentOne.identity.employee_id = 'E1';
    currentTwo.identity.employee_id = 'E2';
    currentOne.calls = { ...currentOne.calls, total_handled: 100, aht_raw: '00:03:00' };
    currentTwo.calls = { ...currentTwo.calls, total_handled: 300, aht_raw: '00:02:00' };
    previous.calls = { ...previous.calls, total_handled: 400, aht_raw: '00:03:00' };
    currentOne.raw_data = { 'T.AHT': '00:02:30' };
    currentTwo.raw_data = { 'T.AHT': '00:02:30' };
    previous.raw_data = { 'T.AHT': '00:02:30' };

    const aht = buildTeamKpiAnalysis(
      [currentOne, currentTwo],
      [previous],
      { includeAht: true, baselineRecords: [previous, currentOne, currentTwo] },
    ).find((kpi) => kpi.key === 'aht')!;

    expect(aht.actual).toBeCloseTo(2.25);
    expect(aht.target).toBeCloseTo(2.5);
    expect(aht.previousActual).toBeCloseTo(3);
    expect(aht.lowerBetter).toBe(true);
    expect(aht.movementPositive).toBe(true);
    expect(aht.weight).toBeNull();
    expect(aht.baselineActual).toBeCloseTo(2.25);
    expect(aht.baselineMonth).toBe('June');
    expect(aht.previousBaselineActual).toBeCloseTo(3);
    expect(aht.previousBaselineMonth).toBe('May');
    expect(aht.isNewBaseline).toBe(true);
  });

  it('promotes a strictly better current result over the previous historical baseline', () => {
    const april = record('April', .68, .09);
    const may = record('May', .7, .1);
    const june = record('June', .723, .1);

    const [booking] = buildTeamKpiAnalysis([june], [may], { baselineRecords: [april, may, june] });

    expect(booking.baselineActual).toBeCloseTo(.723);
    expect(booking.baselineMonth).toBe('June');
    expect(booking.previousBaselineActual).toBeCloseTo(.7);
    expect(booking.previousBaselineMonth).toBe('May');
    expect(booking.isNewBaseline).toBe(true);
  });

  it('does not use a future month when calculating a historical baseline', () => {
    const april = record('April', .68, .09);
    const may = record('May', .7, .1);
    const june = record('June', .8, .1);

    const [booking] = buildTeamKpiAnalysis([may], [april], { baselineRecords: [april, may, june] });

    expect(booking.baselineActual).toBeCloseTo(.7);
    expect(booking.baselineMonth).toBe('May');
    expect(booking.previousBaselineActual).toBeCloseTo(.68);
    expect(booking.previousBaselineMonth).toBe('April');
    expect(booking.isNewBaseline).toBe(true);
  });

  it('uses the active team weight configuration when records do not carry KPI weights', () => {
    const current = record('June', .58, .08);
    current.identity.team = 'Outbound';
    current.kpi_values = undefined;
    current.raw_data = {
      'T.Attend%': '55',
      'T.Booking%': '46',
      'T.Quality%': '95',
      'T.Reachability%': '75',
    };

    const analysis = buildTeamKpiAnalysis(
      [current],
      [],
      { teamWeights: { Attend: .7, Booking: .1, Quality: .1, Other: .1 } },
    );
    const weights = Object.fromEntries(analysis.map((kpi) => [kpi.label, kpi.weight]));

    expect(weights['Attendance Rate']).toBe(.7);
    expect(weights['Booking Rate']).toBe(.1);
    expect(weights['Quality Score']).toBe(0);
    expect(weights.Reachability).toBe(.2);
  });
});
