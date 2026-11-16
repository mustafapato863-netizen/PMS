import { describe, expect, it } from 'vitest';
import { formatActionRootCauseNote, parseActionRootCauseMeta } from './actionNoteFormatter';

describe('actionNoteFormatter', () => {
  it('parses valid __pms_meta__: payloads into structured metadata', () => {
    const encoded =
      '__pms_meta__:{"main_issue":"AHT at 3.12 min vs 2.50 min target","owner":"Inbound Team Leader","expected_impact":"+3.5 pts agent score"}';

    expect(parseActionRootCauseMeta(encoded)).toEqual({
      mainIssue: 'AHT at 3.12 min vs 2.50 min target',
      owner: 'Inbound Team Leader',
      expectedImpact: '+3.5 pts agent score',
      isEncoded: true,
    });

    expect(formatActionRootCauseNote(encoded)).toBe(
      'AHT at 3.12 min vs 2.50 min target · Owner: Inbound Team Leader · Expected impact: +3.5 pts agent score',
    );
  });

  it('omits missing optional metadata segments when formatting encoded notes', () => {
    const encoded = '__pms_meta__:{"main_issue":"Booking Rate gap","owner":"QA Lead"}';

    expect(formatActionRootCauseNote(encoded)).toBe('Booking Rate gap · Owner: QA Lead');
  });

  it('returns plain strings unchanged and marks isEncoded=false', () => {
    expect(parseActionRootCauseMeta('  AHT gap across afternoon shifts  ')).toEqual({
      mainIssue: 'AHT gap across afternoon shifts',
      owner: '',
      expectedImpact: '',
      isEncoded: false,
    });

    expect(formatActionRootCauseNote('AHT gap across afternoon shifts')).toBe(
      'AHT gap across afternoon shifts',
    );
  });

  it('handles empty, nullish, and malformed JSON safely without throwing', () => {
    expect(parseActionRootCauseMeta(null)).toEqual({
      mainIssue: '',
      owner: '',
      expectedImpact: '',
      isEncoded: false,
    });
    expect(parseActionRootCauseMeta(undefined)).toEqual({
      mainIssue: '',
      owner: '',
      expectedImpact: '',
      isEncoded: false,
    });
    expect(formatActionRootCauseNote('')).toBe('');
    expect(formatActionRootCauseNote('   ')).toBe('');

    const malformed = '__pms_meta__:{not-valid-json';
    expect(parseActionRootCauseMeta(malformed)).toEqual({
      mainIssue: malformed,
      owner: '',
      expectedImpact: '',
      isEncoded: false,
    });
    expect(formatActionRootCauseNote(malformed)).toBe(malformed);

    const nonObject = '__pms_meta__:["a"]';
    expect(parseActionRootCauseMeta(nonObject)).toEqual({
      mainIssue: nonObject,
      owner: '',
      expectedImpact: '',
      isEncoded: false,
    });
  });
});
