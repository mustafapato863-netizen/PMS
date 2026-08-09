export const MANAGEMENT_DATA_CHANGED_EVENT = 'pms:management-data-changed';

export function notifyManagementDataChanged() {
  window.dispatchEvent(new Event(MANAGEMENT_DATA_CHANGED_EVENT));
}
