import type { ActionStatus } from '../../types';

export const ACTION_STATUSES: ActionStatus[] = ['Open', 'In Progress', 'Completed', 'Cancelled'];

export function canEditActionFollowUp(role: string | null | undefined): boolean {
  return role === 'Admin' || role === 'Manager';
}

export function daysUntilDue(dueDate: string, today = new Date()): number {
  const due = new Date(`${dueDate.slice(0, 10)}T00:00:00`);
  const start = new Date(today);
  start.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - start.getTime()) / 86_400_000);
}

export function dueBadgeLabel(dueDate: string | null | undefined, daysToDue?: number | null, today = new Date()): string {
  if (!dueDate) return 'No due date';
  const days = typeof daysToDue === 'number' ? daysToDue : daysUntilDue(dueDate, today);
  if (days < 0) {
    const overdue = Math.abs(days);
    return overdue === 1 ? '1 day overdue' : `${overdue} days overdue`;
  }
  if (days === 0) return 'Due today';
  return days === 1 ? '1 day left' : `${days} days left`;
}

export function todayIso(today = new Date()): string {
  const local = new Date(today.getTime() - today.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}
