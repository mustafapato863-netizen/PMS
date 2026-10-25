/** Placeholder shown for a stored action that has no due date. Hidden only while presenting. */
export const EMPTY_DUE_DATE_LABEL = 'No due date';

/**
 * Edit buttons, add-action composers, and empty placeholders stay out of a live presentation.
 * Saved action content is not a control, so this never decides whether an action card renders.
 */
export function showPresentationControl(
  presentationMode: boolean,
): boolean {
  return !presentationMode;
}

/** A real stored value stays visible. An empty placeholder does not, once Presentation Mode is on. */
export function showStoredPlaceholder(
  value: string | null | undefined,
  presentationMode: boolean,
): boolean {
  if (!presentationMode) return true;
  const trimmed = value?.trim() ?? '';
  return trimmed.length > 0 && trimmed !== EMPTY_DUE_DATE_LABEL;
}

/**
 * While presenting, drop a section that would only be an empty composer or a
 * "nothing recorded" note. Saved actions keep the section on screen.
 */
export function showActionSection(
  savedCount: number,
  presentationMode: boolean,
): boolean {
  if (!presentationMode) return true;
  return savedCount > 0;
}
