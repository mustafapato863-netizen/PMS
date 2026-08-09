import { ArrowLeft, Check, ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import CustomDropdown from '../common/CustomDropdown';
import PerformanceLevelFilter from '../common/PerformanceLevelFilter';
import Breadcrumb from '../common/Breadcrumb';
import type { BreadcrumbItem } from '../common/Breadcrumb';
import type { LocationKey, PerformanceLevelFilter as PerformanceLevel, PreApprovalsWorkflowFilter, CallCenterChannelFilter, RcmDomainFilter, RcmGroupFilter } from '../../types';
import { PRE_APPROVALS_WORKFLOW_LABELS, CALL_CENTER_CHANNEL_LABELS, RCM_DOMAIN_LABELS, RCM_GROUP_LABELS } from '../../types';

interface TeamHeaderProps {
  displayName: string;
  month: string;
  uniqueMonths: string[];
  setMonth: (month: string) => void;
  region: 'All' | 'EGY' | 'UAE';
  setRegion: (region: 'All' | 'EGY' | 'UAE') => void;
  location: LocationKey;
  setLocation: (location: LocationKey) => void;
  branchSelections?: LocationKey[];
  setBranchSelections?: (locations: LocationKey[]) => void;
  multiBranchFilter?: boolean;
  onBack: () => void;
  showRegionFilter?: boolean;
  showPreApprovalsWorkflowFilter?: boolean;
  preApprovalsWorkflow?: PreApprovalsWorkflowFilter;
  setPreApprovalsWorkflow?: (workflow: PreApprovalsWorkflowFilter) => void;
  showCallCenterChannelFilter?: boolean;
  callCenterChannel?: CallCenterChannelFilter;
  setCallCenterChannel?: (channel: CallCenterChannelFilter) => void;
  showRcmDomainFilter?: boolean;
  rcmDomain?: RcmDomainFilter;
  setRcmDomain?: (domain: RcmDomainFilter) => void;
  showRcmGroupFilter?: boolean;
  rcmGroup?: RcmGroupFilter;
  setRcmGroup?: (group: RcmGroupFilter) => void;
  performanceLevel: PerformanceLevel;
  setPerformanceLevel: (level: PerformanceLevel) => void;
  disabledPerformanceLevel?: boolean;
}

const TeamHeader = ({
  displayName,
  month,
  uniqueMonths,
  setMonth,
  region,
  setRegion,
  location,
  setLocation,
  branchSelections = ['all'],
  setBranchSelections,
  multiBranchFilter = false,
  onBack,
  showRegionFilter = true,
  showPreApprovalsWorkflowFilter = false,
  preApprovalsWorkflow = 'all',
  setPreApprovalsWorkflow,
  showCallCenterChannelFilter = false,
  callCenterChannel = 'all',
  setCallCenterChannel,
  showRcmDomainFilter = false,
  rcmDomain = 'all',
  setRcmDomain,
  showRcmGroupFilter = false,
  rcmGroup = 'all',
  setRcmGroup,
  performanceLevel,
  setPerformanceLevel,
  disabledPerformanceLevel,
}: TeamHeaderProps) => {
  const [branchesOpen, setBranchesOpen] = useState(false);
  const branchesRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (branchesRef.current && !branchesRef.current.contains(event.target as Node)) setBranchesOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const branchOptions: Array<{ value: LocationKey; label: string }> = [
    { value: 'all', label: 'All Branches' },
    { value: 'dubai', label: 'Dubai' },
    { value: 'sharjah', label: 'Sharjah (Sharqa)' },
    { value: 'ajman', label: 'Ajman' },
    { value: 'clinics', label: 'Clinics' },
  ];
  const selectedBranches = branchSelections.includes('all') ? [] : branchSelections;
  const branchLabel = selectedBranches.length === 0
    ? 'All Branches'
    : selectedBranches.length === 1
      ? branchOptions.find((option) => option.value === selectedBranches[0])?.label || '1 Branch'
      : `${selectedBranches.length} Branches`;
  const toggleBranch = (value: LocationKey) => {
    if (!setBranchSelections) return;
    if (value === 'all') {
      setBranchSelections(['all']);
      return;
    }
    const next = selectedBranches.includes(value)
      ? selectedBranches.filter((branch) => branch !== value)
      : [...selectedBranches, value];
    setBranchSelections(next.length > 0 ? next : ['all']);
  };
  const breadcrumbItems: BreadcrumbItem[] = [
    { label: 'Dashboard', href: '/executive', icon: 'home' },
    { label: 'Team Performance', icon: 'teams' },
    ...(displayName && displayName !== 'All Teams'
      ? [{ label: displayName, icon: 'team' as const }]
      : []),
    ...(month && month !== 'All'
      ? [{ label: month, icon: 'calendar' as const }]
      : []),
  ];

  // Make the last item always the actual current page (no href)
  const finalCrumbs: BreadcrumbItem[] = breadcrumbItems.map((item, idx) =>
    idx === breadcrumbItems.length - 1 ? { ...item, href: undefined } : item
  );

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <button
          onClick={onBack}
          aria-label="Go back"
          className="p-2 hover:bg-[var(--bg-sunken)] rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer shrink-0 mt-0.5"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-[var(--text-primary)] leading-tight">
            {displayName}{performanceLevel !== 'All' && !disabledPerformanceLevel ? ` · ${performanceLevel}` : ''}
          </h2>
          <Breadcrumb items={finalCrumbs} />
        </div>
      </div>
      <div className="flex w-full flex-wrap items-center gap-2.5 sm:gap-3 xl:w-auto xl:justify-end shrink-0">
        <PerformanceLevelFilter value={performanceLevel} onChange={setPerformanceLevel} disabled={disabledPerformanceLevel} />

        {showPreApprovalsWorkflowFilter && setPreApprovalsWorkflow && (
          <CustomDropdown
            value={preApprovalsWorkflow}
            options={Object.entries(PRE_APPROVALS_WORKFLOW_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(value) => setPreApprovalsWorkflow(value as PreApprovalsWorkflowFilter)}
            size="md"
          />
        )}

        {showCallCenterChannelFilter && setCallCenterChannel && (
          <CustomDropdown
            value={callCenterChannel}
            options={Object.entries(CALL_CENTER_CHANNEL_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(value) => setCallCenterChannel(value as CallCenterChannelFilter)}
            size="md"
          />
        )}

        {showRcmDomainFilter && setRcmDomain && (
          <CustomDropdown
            value={rcmDomain}
            options={Object.entries(RCM_DOMAIN_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(value) => setRcmDomain(value as RcmDomainFilter)}
            ariaLabel="RCM domain"
            size="md"
          />
        )}

        {showRcmGroupFilter && setRcmGroup && (
          <CustomDropdown
            value={rcmGroup}
            options={Object.entries(RCM_GROUP_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(value) => setRcmGroup(value as RcmGroupFilter)}
            ariaLabel="RCM operating group"
            size="md"
          />
        )}
        
        {/* Region Selector */}
        {showRegionFilter && (
          <CustomDropdown
            value={region}
            options={[
              { value: 'All', label: 'All Regions' },
              { value: 'EGY', label: 'Egypt (EGY)' },
              { value: 'UAE', label: 'UAE' },
            ]}
            onChange={(val) => setRegion(val as 'All' | 'EGY' | 'UAE')}
            size="md"
          />
        )}

        {/* Branch selector shared by the merged OP Final and IP Final views. */}
        {multiBranchFilter ? (
          <div ref={branchesRef} className="relative inline-block">
            <button
              type="button"
              aria-label="Branches"
              onClick={() => setBranchesOpen((open) => !open)}
              className="flex items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] shadow-sm transition hover:border-blue-300 hover:shadow-md"
            >
              <span className="max-w-[150px] truncate">{branchLabel}</span>
              <ChevronDown size={13} className={branchesOpen ? 'rotate-180 text-blue-500' : 'text-[var(--text-muted)]'} />
            </button>
            {branchesOpen && (
              <div className="absolute right-0 z-50 mt-2 min-w-[190px] rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-1.5 shadow-[0_16px_40px_rgba(15,23,42,0.18)]">
                {branchOptions.map((option) => {
                  const checked = option.value === 'all' ? selectedBranches.length === 0 : selectedBranches.includes(option.value);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => toggleBranch(option.value)}
                      className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-semibold transition-colors ${checked ? 'bg-blue-500/10 text-blue-600' : 'text-[var(--text-primary)] hover:bg-[var(--bg-sunken)]'}`}
                    >
                      <span>{option.label}</span>
                      {checked && <Check size={14} className="text-blue-500" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <CustomDropdown
            value={location}
            options={branchOptions}
            onChange={(val) => setLocation(val as LocationKey)}
            size="md"
          />
        )}

        {/* Month Selector */}
        <CustomDropdown
          value={month}
          options={[
            { value: 'All', label: 'All Months' },
            ...uniqueMonths.map((m) => ({ value: m, label: m })),
          ]}
          onChange={(val) => setMonth(String(val))}
          size="md"
        />

      </div>
    </div>
  );
};

export default TeamHeader;
