import './PageEnhancements.css';
import { motion } from 'framer-motion';
import { ShieldAlert } from 'lucide-react';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { useUserRole } from '../context/RoleContext';
import { canAccessSettingsContent } from '../lib/access';
import { SettingsLayout } from '../components/settings/SettingsLayout';
import { DataManagementPanel } from '../components/settings/DataManagementPanel';
import { EvaluationSettingsPanel } from '../components/settings/EvaluationSettingsPanel';
import { UserManagementPanel } from '../components/settings/UserManagementPanel';
import { CorrectiveActionDataPanel } from '../components/settings/CorrectiveActionDataPanel';
import { DataSnapshotPanel } from '../components/settings/DataSnapshotPanel';
import { SystemErrorsPanel } from '../components/settings/SystemErrorsPanel';
import { AdminOverview } from '../components/settings/shell/AdminOverview';
import { AdminPageHeader } from '../components/settings/shell/AdminPageHeader';
import { pageForLegacyTab, pageForSlug, settingsPathFor } from '../components/settings/shell/settingsNavigation';

const SettingsView = () => {
  const { role } = useUserRole();
  const { section } = useParams();
  const { search } = useLocation();
  // Admin-only content. Every other role, General Manager included, gets the soft-lock panel.
  const isAdmin = canAccessSettingsContent(role);

  if (!isAdmin) {
    return (
      <div className="flex min-h-[55vh] items-center justify-center p-6">
        <div className="glass-panel max-w-lg rounded-3xl border border-amber-500/20 p-8 text-center shadow-sm">
          <ShieldAlert size={34} className="mx-auto text-amber-500" />
          <h1 className="mt-4 text-xl font-black text-[var(--text-primary)]">Administrator access required</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">Settings and administrative configuration are only available to Admin users.</p>
        </div>
      </div>
    );
  }

  const page = pageForSlug(section);
  if (page === null) {
    // `/settings` opens the overview, or the section a legacy `?tab=` shortcut names. An unknown slug opens the overview.
    // The query string is kept so that Evaluation's year and month survive the redirect.
    const legacyPage = section === undefined ? pageForLegacyTab(new URLSearchParams(search).get('tab')) : null;
    return <Navigate replace to={{ pathname: settingsPathFor(legacyPage ?? 'overview'), search }} />;
  }

  return (
    <motion.main initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="app-page-shell rf-page rf-page--settings">
      <AdminPageHeader title="Administration" description="Configure data, evaluation settings, users and system health." />
      <SettingsLayout activePage={page}>
        {page === 'overview' && <AdminOverview />}
        {page === 'upload' && (
          <>
            <DataManagementPanel />
            <DataSnapshotPanel />
          </>
        )}
        {page === 'corrective_actions' && <CorrectiveActionDataPanel />}
        {page === 'kpis' && <EvaluationSettingsPanel />}
        {page === 'users' && <UserManagementPanel />}
        {page === 'system_errors' && <SystemErrorsPanel />}
      </SettingsLayout>
    </motion.main>
  );
};

export default SettingsView;
