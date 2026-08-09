import {
  AlertOctagon,
  AlertTriangle,
  BadgeCheck,
  Code,
  Headphones,
  HeartPulse,
  Pill,
  RefreshCw,
  Send,
  Target,
  UserCheck,
  Megaphone,
  DollarSign,
  Building2,
  Users,
  Activity,
  Briefcase,
  FolderKanban,
  BadgeDollarSign,
  Handshake,
  Syringe,
  Timer,
  ClipboardCheck,
  PhoneCall,
} from 'lucide-react';

export const getTeamIcon = (teamName: string) => {
  const norm = teamName.trim().toLowerCase();
  if (norm === 'pmo' || norm.includes('pmo') || norm.includes('project management')) return <FolderKanban size={17} />;
  if (norm === 'crm' || norm.includes('crm') || norm.includes('customer relationship')) return <Handshake size={17} />;
  if (norm.includes('rcm') || norm.includes('revenue cycle')) return <BadgeDollarSign size={17} />;
  if (norm.includes('marketing')) return <Megaphone size={17} />;
  if (norm.includes('finance') || norm.includes('financial')) return <DollarSign size={17} />;
  if (norm.includes('inbound uae')) return <HeartPulse size={17} />;
  if (norm.includes('call center')) return <PhoneCall size={17} />;
  if (norm.includes('inbound')) return <UserCheck size={17} />;
  if (norm.includes('outbound')) return <AlertOctagon size={17} />;
  if (norm.includes('pre-approvals op final')) return <ClipboardCheck size={17} />;
  if (norm.includes('pre-approvals op dubai')) return <ClipboardCheck size={17} />;
  if (norm.includes('pre-approvals ip elective dubai')) return <Timer size={17} />;
  if (norm.includes('pre-approvals ip final dubai')) return <BadgeCheck size={17} />;
  if (norm.includes('pre-approvals op final shj') || norm.includes('pre-approvals op final shjajm')) return <ClipboardCheck size={17} />;
  if (norm.includes('pre-approvals ip final shj') || norm.includes('pre-approvals ip final shjajm')) return <Activity size={17} />;
  if (norm.includes('pre-approvals ip final')) return <Activity size={17} />;
  if (norm.includes('pre-approvals')) return <AlertTriangle size={17} />;
  if (norm.includes('sales')) return <Target size={17} />;
  if (norm.includes('coding')) return <Code size={17} />;
  if (norm.includes('csr')) return <Headphones size={17} />;
  if (norm.includes('pharmacy')) return <Pill size={17} />;
  if (norm.includes('nursing') || norm.includes('nurse')) return <Syringe size={17} />;
  if (norm.includes('re-submission')) return <RefreshCw size={17} />;
  if (norm.includes('submission')) return <Send size={17} />;
  if (norm.includes('executive') || norm.includes('management')) return <Building2 size={17} />;
  if (norm.includes('hr') || norm.includes('people')) return <Users size={17} />;
  if (norm.includes('operation')) return <Activity size={17} />;
  return <Briefcase size={17} />;
};

export const TEAM_ITEMS = [
  { name: 'Call Center', path: '/team/call-center', icon: <PhoneCall size={17} />, team: 'Call Center', region: 'egy' },
  { name: 'Inbound UAE', path: '/team/inbound-uae', icon: <HeartPulse size={17} />, team: 'Inbound UAE', region: 'uae' },
  { name: 'Sales', path: '/team/sales', icon: <Target size={17} />, team: 'Sales', region: 'uae' },
  { name: 'CSR', path: '/team/csr', icon: <Headphones size={17} />, team: 'CSR', region: 'uae' },
  { name: 'Pharmacy', path: '/team/pharmacy', icon: <Pill size={17} />, team: 'Pharmacy', region: 'uae' },
] as const;
