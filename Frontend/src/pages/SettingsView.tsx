import { useState } from 'react';
import { motion } from 'framer-motion';
import { Settings, ShieldAlert } from 'lucide-react';
import { useUserRole } from '../context/RoleContext';
import { SettingsLayout } from '../components/settings/SettingsLayout';
import { DataManagementPanel } from '../components/settings/DataManagementPanel';
import { KPIConfigPanel } from '../components/settings/KPIConfigPanel';
import { UserManagementPanel } from '../components/settings/UserManagementPanel';
import { CorrectiveActionDataPanel } from '../components/settings/CorrectiveActionDataPanel';
import type { SettingsSection } from '../components/settings/types';
import TeamManagementView from './TeamManagementView';

const SettingsView = () => {
  const { role } = useUserRole();
  const [activeSection, setActiveSection] = useState<SettingsSection>('upload');
  const isAdmin = role === 'Admin';

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

  return (
    <motion.main initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="app-page-shell">
      <header className="flex items-center gap-3">
        <div className="rounded-2xl bg-blue-500/10 p-3 text-blue-600 dark:text-blue-400"><Settings size={22} /></div>
        <div><h1 className="text-2xl font-black tracking-tight text-[var(--text-primary)]">Settings & Administration</h1><p className="mt-1 text-xs text-[var(--text-muted)]">Manage data, KPI definitions, users and team onboarding.</p></div>
      </header>
      <SettingsLayout activeSection={activeSection} onSectionChange={setActiveSection}>
        {activeSection === 'upload' && <DataManagementPanel />}
        {activeSection === 'corrective_actions' && <CorrectiveActionDataPanel />}
        {activeSection === 'kpis' && <KPIConfigPanel />}
        {activeSection === 'users' && <UserManagementPanel />}
        {activeSection === 'teams' && <div className="glass-panel rounded-3xl p-5 shadow-sm"><TeamManagementView /></div>}
      </SettingsLayout>
    </motion.main>
  );
};

export default SettingsView;
