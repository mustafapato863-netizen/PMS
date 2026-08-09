import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import Sidebar from './components/common/Sidebar';
import Header from './components/common/Header';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/auth';
import { RoleProvider, useUserRole } from './context/RoleContext';
import { ThemeProvider } from './context/ThemeContext';
import { useNotificationSocket } from './hooks/useNotificationSocket';
import { REALTIME_ENABLED } from './config';
import AppErrorBoundary from './components/common/AppErrorBoundary';
import WorkspaceLoader from './components/common/WorkspaceLoader';
import { PageLoadingSkeleton } from './components/common/SkeletonLoader';

const ExecutiveView = lazy(() => import('./pages/ExecutiveView'));
const MarketingTeamRoute = lazy(() => import('./pages/MarketingTeamRoute'));
const TeamDashboardView = lazy(() => import('./pages/TeamDashboardView'));
const EmployeeProfileView = lazy(() => import('./pages/EmployeeProfileView'));
const SettingsView = lazy(() => import('./pages/SettingsView'));
const TeamManagementView = lazy(() => import('./pages/TeamManagementView'));
const LoginView = lazy(() => import('./pages/LoginView'));
const ReportsView = lazy(() => import('./pages/ReportsView'));
const ReportBuilderView = lazy(() => import('./pages/ReportBuilderView'));
const ReportPreviewView = lazy(() => import('./pages/ReportPreviewView'));
const InsightsView = lazy(() => import('./pages/InsightsView'));
const PlanningView = lazy(() => import('./pages/PlanningView'));
const NotFound = lazy(() => import('./pages/NotFound'));

const RouteLoadingFallback = () => <PageLoadingSkeleton variant="dashboard" label="Loading page" />;

interface RouteGuardProps {
  children: React.ReactNode;
  allowedRoles: string[];
}

function RouteGuard({ children, allowedRoles }: RouteGuardProps) {
  const { role } = useUserRole();
  if (!allowedRoles.includes(role)) {
    return <Navigate to="/executive" replace />;
  }
  return <>{children}</>;
}

function AnimatedRoutes() {
  const location = useLocation();
  const { currentUser } = useAuth();

  if (currentUser?.role === 'Agent') {
    return (
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route
            path="/employee/:employeeId"
            element={<Suspense fallback={<RouteLoadingFallback />}><EmployeeProfileView /></Suspense>}
          />
          <Route path="*" element={<Suspense fallback={<RouteLoadingFallback />}><NotFound /></Suspense>} />
        </Routes>
      </AnimatePresence>
    );
  }

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/executive" replace />} />

        {/* Login Page Redirect when authenticated */}
        <Route path="/login" element={<Navigate to="/executive" replace />} />

        {/* Page 1: Executive Summary */}
        <Route path="/executive" element={<Suspense fallback={<RouteLoadingFallback />}><ExecutiveView /></Suspense>} />

        {/* Page 2: Team Dashboard — /team/:teamId */}
        <Route path="/team/marketing" element={<Suspense fallback={<RouteLoadingFallback />}><MarketingTeamRoute /></Suspense>} />
        <Route path="/team/:teamId" element={<Suspense fallback={<RouteLoadingFallback />}><TeamDashboardView /></Suspense>} />

        {/* /operational redirects to /team/all */}
        <Route path="/operational" element={<Navigate to="/team/all" replace />} />

        {/* Page 3: Employee Profile */}
        <Route path="/employee/:employeeId" element={<Suspense fallback={<RouteLoadingFallback />}><EmployeeProfileView /></Suspense>} />

        {/* Team Management (Admin only) */}
        <Route
          path="/team-management"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><TeamManagementView /></Suspense>
            </RouteGuard>
          }
        />

        {/* Settings */}
        <Route path="/settings" element={<Suspense fallback={<RouteLoadingFallback />}><SettingsView /></Suspense>} />

        {/* Reporting workspace */}
        <Route
          path="/reports"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><ReportsView /></Suspense>
            </RouteGuard>
          }
        />
        <Route
          path="/reports/new"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><ReportBuilderView /></Suspense>
            </RouteGuard>
          }
        />
        <Route
          path="/reports/:reportId/edit"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><ReportBuilderView /></Suspense>
            </RouteGuard>
          }
        />
        <Route
          path="/reports/:reportId/preview"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><ReportPreviewView /></Suspense>
            </RouteGuard>
          }
        />

        {/* Evidence-based decision support */}
        <Route
          path="/insights"
          element={
            <RouteGuard allowedRoles={['Admin']}>
              <Suspense fallback={<RouteLoadingFallback />}><InsightsView /></Suspense>
            </RouteGuard>
          }
        />
        <Route path="/planning" element={<RouteGuard allowedRoles={['Admin']}><Suspense fallback={<RouteLoadingFallback />}><PlanningView /></Suspense></RouteGuard>} />

        {/* 404 Page Not Found */}
        <Route path="*" element={<Suspense fallback={<RouteLoadingFallback />}><NotFound /></Suspense>} />
      </Routes>
    </AnimatePresence>
  );
}

function AppContent() {
  const { currentUser, isAppInitializing, initializationStatus, initializationError } = useAuth();
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem('pms.sidebar.collapsed') === 'true';
    } catch {
      return false;
    }
  });
  const isReportBuilder = location.pathname === '/reports/new' || /^\/reports\/[^/]+\/edit$/.test(location.pathname);

  useEffect(() => {
    try {
      window.localStorage.setItem('pms.sidebar.collapsed', String(isSidebarCollapsed));
    } catch {
      // Keep the sidebar usable when storage is unavailable (private browsing, embedded webviews, etc.).
    }
  }, [isSidebarCollapsed]);

  // Initialize real-time notifications
  useNotificationSocket(REALTIME_ENABLED && initializationStatus === 'ready');

  if (isAppInitializing) {
    return <WorkspaceLoader />;
  }

  if (initializationStatus === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center px-6" style={{ background: 'var(--bg-base)' }}>
        <div className="max-w-md w-full rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-8 text-center shadow-xl space-y-4">
          <h2 className="text-2xl font-extrabold text-[var(--text-primary)]">Unable to prepare your workspace.</h2>
          <p className="text-sm text-[var(--text-secondary)]">{initializationError || 'Please retry or log out.'}</p>
          <div className="flex items-center justify-center gap-3">
            <button className="px-4 py-2 rounded-xl bg-blue-600 text-white font-bold" onClick={() => window.location.reload()}>
              Retry
            </button>
            <button className="px-4 py-2 rounded-xl border border-[var(--border-light)] font-bold" onClick={() => { window.location.href = '/login'; }}>
              Logout
            </button>
          </div>
        </div>
      </div>
    );
  }

  // If not logged in, render only LoginView and redirect all other paths to /login
  if (!currentUser) {
    return (
      <Routes>
        <Route path="/login" element={<LoginView />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <div className="flex min-h-screen font-sans selection:bg-blue-500/30 selection:text-blue-900 relative" style={{ backgroundColor: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      {/* Ambient Animated Background Blobs */}
      <div
        className="fixed inset-0 pointer-events-none z-0 hidden overflow-hidden sm:block"
        style={{ contain: 'strict', clipPath: 'inset(0)' }}
      >
        <div className="absolute top-[10%] left-[20%] w-[500px] h-[500px] rounded-full bg-blue-500/3 blur-[140px] animate-blob" />
        <div className="absolute bottom-[15%] right-[10%] w-[600px] h-[600px] rounded-full bg-indigo-500/3 blur-[140px] animate-blob animation-delay-2000" />
        <div className="absolute top-[50%] left-[45%] w-[450px] h-[450px] rounded-full bg-emerald-500/3 blur-[120px] animate-blob animation-delay-4000" />
      </div>

      {!isReportBuilder && (
        <Sidebar
          isOpen={isSidebarOpen}
          setIsOpen={setIsSidebarOpen}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapsed={() => setIsSidebarCollapsed((collapsed) => !collapsed)}
        />
      )}


      {/* Mobile Overlay */}
      {!isReportBuilder && isSidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/50 backdrop-blur-sm xl:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <main className={`relative flex min-h-screen min-w-0 w-full flex-1 flex-col transition-[margin,width] duration-300 ${isReportBuilder ? '' : isSidebarCollapsed ? 'xl:ml-[84px] xl:w-[calc(100%-84px)]' : 'xl:ml-[272px] xl:w-[calc(100%-272px)]'}`}>
        {!isReportBuilder && <Header onMenuClick={() => setIsSidebarOpen(true)} />}
        <div className={`flex-1 w-full relative z-10 ${isReportBuilder ? 'p-3 sm:p-4' : 'p-3 sm:p-4 md:p-6 lg:p-8'}`}>
          <AnimatedRoutes />
        </div>
      </main>

    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RoleProvider>
          <AppErrorBoundary>
            <Router>
              <AppContent />
            </Router>
          </AppErrorBoundary>
        </RoleProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;

