import { describe, expect, it } from 'vitest';
import { dedupedNote, distinctNoteSentences, noteSentences } from './evaluationNotes';

describe('noteSentences', () => {
  it('splits after sentence punctuation and keeps the punctuation', () => {
    expect(noteSentences('First sentence. Second one! Third?')).toEqual(['First sentence.', 'Second one!', 'Third?']);
  });

  it('ignores empty input and extra whitespace', () => {
    expect(noteSentences('   ')).toEqual([]);
    expect(noteSentences('  One.   Two.  ')).toEqual(['One.', 'Two.']);
  });

  it('does not split decimals or a value with no space after the point', () => {
    expect(noteSentences('Target 0.55 applies.')).toEqual(['Target 0.55 applies.']);
  });
});

describe('distinctNoteSentences', () => {
  it('keeps each distinct sentence once, in the order it first appears', () => {
    const note = 'Draft started from the file baseline. Copied from the approved previous month. Draft started from the file baseline.';
    expect(distinctNoteSentences(note)).toEqual([
      'Draft started from the file baseline.',
      'Copied from the approved previous month.',
    ]);
  });

  it('leaves a note with no repeats exactly as it was', () => {
    expect(distinctNoteSentences('Only one sentence here.')).toEqual(['Only one sentence here.']);
  });

  it('treats differently worded sentences as distinct, so no wording is lost', () => {
    expect(distinctNoteSentences('Saved. Saved again.')).toEqual(['Saved.', 'Saved again.']);
  });

  it('returns nothing for an empty note', () => {
    expect(distinctNoteSentences('')).toEqual([]);
  });
});

describe('dedupedNote', () => {
  it('joins the distinct sentences with single spaces', () => {
    expect(dedupedNote('Repeat me. Repeat me. Keep this.')).toBe('Repeat me. Keep this.');
  });

  it('returns the note unchanged when no sentence repeats', () => {
    expect(dedupedNote('Copied from the approved previous month.')).toBe('Copied from the approved previous month.');
  });
});
