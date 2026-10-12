/**
 * Messages shared by the panel container and its presentation components. They live here so the components
 * never import from the container, which imports them.
 */
export const STALE_SAVE_MESSAGE = 'This draft changed after you opened it. Reload the draft or discard your edits. Nothing was saved.';
export const VERSION_DRIFT_MESSAGE = 'This month is showing a different version from the one you started editing. Reload the draft or discard your edits. Saving will not write that other version.';
export const MISSING_CHECKSUM_MESSAGE = 'Save is unavailable until this draft has a rules checksum. Reload the month. An empty checksum is not sent.';
