import type { QueryClient } from '@tanstack/react-query';
import type { User } from '../../types';
import { notifyManagementDataChanged } from '../../lib/managementDataEvents';
import type { KPITargetItem, KPIWeightItem } from './types';

export interface TeamKPIConfig {
  team: string;
  weights: Record<string, number>;
  targets: Record<string, number>;
  scopes: TeamKPIScope[];
}

export interface TeamKPIScope {
  position: string | null;
  weights: Record<string, number>;
  targets: Record<string, number>;
}

export function mergeKPIConfig(weights: KPIWeightItem[], targets: KPITargetItem[]): TeamKPIConfig[] {
  const teamNames = new Set<string>();
  weights.forEach((item) => { if (item?.team) teamNames.add(item.team); });
  targets.forEach((item) => { if (item?.team) teamNames.add(item.team); });
  return [...teamNames].sort((a, b) => a.localeCompare(b)).map((team) => {
    const weightItem = weights.find((item) => item?.team === team);
    const targetItem = targets.find((item) => item?.team === team);
    const positions = new Set<string>();
    (weightItem?.scopes || []).forEach((scope) => positions.add(scope?.position || ''));
    (targetItem?.scopes || []).forEach((scope) => positions.add(scope?.position || ''));
    const scopes = [...positions].sort((a, b) => a.localeCompare(b)).map((position) => ({
      position: position || null,
      weights: weightItem?.scopes?.find((scope) => (scope?.position || '') === position)?.weights || {},
      targets: targetItem?.scopes?.find((scope) => (scope?.position || '') === position)?.targets || {},
    }));
    return {
      team,
      weights: weightItem?.weights || {},
      targets: targetItem?.targets || {},
      scopes,
    };
  });
}

export function safeUserName(user: Partial<User>) {
  return typeof user.name === 'string' && user.name.trim() ? user.name.trim() : 'Unnamed user';
}

export function userInitials(user: Partial<User>) {
  return safeUserName(user).split(/\s+/).slice(0, 2).map((part) => part[0] || '').join('').toUpperCase();
}

export async function refreshManagementData(queryClient: QueryClient, reload: () => Promise<void>) {
  await Promise.all([reload(), queryClient.invalidateQueries({ queryKey: ['balanced-scorecard'] })]);
  notifyManagementDataChanged();
}
