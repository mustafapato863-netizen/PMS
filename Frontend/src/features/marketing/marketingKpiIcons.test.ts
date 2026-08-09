import { describe, expect, it } from 'vitest';
import {
  Coins,
  DollarSign,
  Download,
  Eye,
  Bug,
  MessageCircle,
  Pencil,
  Percent,
  Repeat2,
  Users,
} from 'lucide-react';
import { getMarketingKpiIcon } from './marketingKpiIcons';

describe('marketing KPI icon mapping', () => {
  it('resolves semantic icons without depending on UI card hardcoding', () => {
    expect(getMarketingKpiIcon({ key: 'mb_cpl', label: 'CPL' })).toBe(DollarSign);
    expect(getMarketingKpiIcon({ key: 'mb_cr', label: 'CR' })).toBe(Percent);
    expect(getMarketingKpiIcon({ key: 'mb_leads', label: 'Leads' })).toBe(Users);
    expect(getMarketingKpiIcon({ key: 'mb_cpv', label: 'CPV' })).toBe(Eye);
    expect(getMarketingKpiIcon({ key: 'mb_revenue', label: 'Revenue' })).toBe(Coins);
    expect(getMarketingKpiIcon({ key: 'mb_app_installs', label: 'App Installs' })).toBe(Download);
    expect(getMarketingKpiIcon({ key: 'video_views', label: 'Video Views' })).toBe(Eye);
    expect(getMarketingKpiIcon({ key: 'bug_resolution_rate', label: 'Error / bug resolution rate' })).toBe(Bug);
    expect(getMarketingKpiIcon({ key: 'response_rate', label: 'Response rate' })).toBe(MessageCircle);
    expect(getMarketingKpiIcon({ key: 'gd_edits_rate', label: 'Edits Rate' })).toBe(Pencil);
    expect(getMarketingKpiIcon({ key: 'rework_rate', label: 'Rework Rate' })).toBe(Repeat2);
  });
});
