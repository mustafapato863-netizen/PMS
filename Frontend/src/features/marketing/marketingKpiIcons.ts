import {
  Activity,
  Bug,
  CalendarCheck,
  Clock,
  Coins,
  DollarSign,
  Download,
  Eye,
  FileText,
  Globe2,
  MessageCircle,
  Pencil,
  Percent,
  Repeat2,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { MarketingKpiConfig } from './types';

interface KpiIconRule {
  tokens: RegExp;
  icon: LucideIcon;
}

const KPI_ICON_RULES: KpiIconRule[] = [
  { tokens: /(cpv|cost per view|video view)/i, icon: Eye },
  { tokens: /(cpl|cost|price|spend)/i, icon: DollarSign },
  { tokens: /(revenue|income|sales value)/i, icon: Coins },
  { tokens: /(download|app install)/i, icon: Download },
  { tokens: /(lead|audience|customer)/i, icon: Users },
  { tokens: /(view|video|impression)/i, icon: Eye },
  { tokens: /(bug|error)/i, icon: Bug },
  { tokens: /(response time|load speed|time|timeliness)/i, icon: Clock },
  { tokens: /(response|message|social)/i, icon: MessageCircle },
  { tokens: /(edit|revision)/i, icon: Pencil },
  { tokens: /rework/i, icon: Repeat2 },
  { tokens: /(brand|consistency|guideline|compliance)/i, icon: ShieldCheck },
  { tokens: /(schedule|delivery)/i, icon: CalendarCheck },
  { tokens: /(uptime|website|organic)/i, icon: Globe2 },
  { tokens: /(growth|traffic)/i, icon: TrendingUp },
  { tokens: /(content|project|request)/i, icon: FileText },
  { tokens: /(conversion|\bcr\b|rate|percentage|ratio)/i, icon: Percent },
];

export const getMarketingKpiIcon = (kpi: Pick<MarketingKpiConfig, 'key' | 'label'>): LucideIcon => {
  const semanticName = `${kpi.key} ${kpi.label}`;
  return KPI_ICON_RULES.find((rule) => rule.tokens.test(semanticName))?.icon || Activity;
};
