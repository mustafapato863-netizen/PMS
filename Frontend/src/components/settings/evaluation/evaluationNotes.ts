/** Splits a note into sentences, keeping the punctuation. A sentence ends at ., ! or ? followed by whitespace. */
export function noteSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);
}

/**
 * Each distinct sentence once, in the order it first appears. Repeats are removed, and the rest of the note keeps its wording.
 * A repeated sentence in a stored note is a data artefact; it is not a message to show twice.
 */
export function distinctNoteSentences(text: string): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const sentence of noteSentences(text)) {
    if (seen.has(sentence)) continue;
    seen.add(sentence);
    unique.push(sentence);
  }
  return unique;
}

export function dedupedNote(text: string): string {
  return distinctNoteSentences(text).join(' ');
}
