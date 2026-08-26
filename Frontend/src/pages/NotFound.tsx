import './PageEnhancements.css';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Compass, ArrowLeft, Home, User, HeartPulse } from 'lucide-react';
import { useAuth } from '../context/auth';
import { useUserRole } from '../context/RoleContext';

const NotFound = () => {
  const { currentUser } = useAuth();
  const { role } = useUserRole();

  const isAgent = role === 'Agent';
  const ownEmployeeId = currentUser?.employee_id || currentUser?.id || '';
  const homePath = isAgent ? `/employee/${ownEmployeeId}` : '/executive';
  const homeLabel = isAgent ? 'Go to My Profile' : 'Return to Dashboard';

  const handleGoBack = () => {
    window.history.back();
  };

  return (
    <div
      className="rf-not-found min-h-screen flex items-center justify-center p-6 bg-[var(--bg-base)] transition-colors duration-300 relative overflow-hidden"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* Background Decorative Blobs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" style={{ animationDelay: '2s' }} />

      <div className="max-w-xl w-full text-center relative z-10">
        {/* Logo block */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="flex items-center justify-center gap-2.5 mb-8"
        >
          <div className="rounded-xl border border-blue-400/20 bg-gradient-to-br from-blue-500 to-indigo-600 p-2 shadow-[0_4px_12px_rgba(59,130,246,0.30)]">
            <HeartPulse size={20} className="text-white" />
          </div>
          <div>
            <span className="text-sm font-extrabold tracking-tight text-[var(--text-primary)]">SGH Hub</span>
            <span className="text-[9px] font-bold uppercase tracking-widest text-blue-600 block leading-none mt-0.5">Intelligence</span>
          </div>
        </motion.div>

        {/* Premium Glassmorphic Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="rf-not-found-card rounded-[32px] border border-[var(--border-light)] bg-[var(--bg-surface)]/95 p-10 md:p-12 shadow-[0_20px_50px_rgba(15,23,42,0.08)]"
        >
          {/* Animated Illustration */}
          <div className="relative flex justify-center mb-8">
            <div
              className="absolute inset-0 mx-auto h-32 w-32 rounded-full bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 blur-xl pointer-events-none"
              aria-hidden="true"
            />
            <div
              className="relative flex h-24 w-24 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-[0_12px_30px_rgba(59,130,246,0.25)]"
            >
              <Compass className="text-white w-12 h-12 stroke-[1.5]" />
              {/* Absctract 404 tag badge */}
              <div className="absolute -bottom-2 -right-2 px-2.5 py-1 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-light)] text-[10px] font-extrabold text-blue-600 tracking-wider shadow-md uppercase">
                Code 404
              </div>
            </div>
          </div>

          <h1 className="text-6xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400 mb-4">
            Lost in Space
          </h1>
          
          <h2 className="text-xl font-extrabold text-[var(--text-primary)] mb-3">
            The page you are looking for does not exist.
          </h2>
          
          <p className="text-sm text-[var(--text-muted)] max-w-sm mx-auto mb-10 leading-relaxed font-semibold">
            It looks like this URL was incorrect, expired, or you might not have authorization to access this specific area.
          </p>

          {/* Action Callouts */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={handleGoBack}
              className="flex min-h-12 w-full sm:w-auto items-center justify-center gap-2 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] hover:bg-[var(--bg-sunken)] px-6 py-3 text-sm font-extrabold text-[var(--text-secondary)] shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <ArrowLeft size={16} />
              <span>Go Back</span>
            </button>

            <Link
              to={homePath}
              className="flex min-h-12 w-full sm:w-auto items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 px-6 py-3 text-sm font-extrabold text-white shadow-[0_4px_14px_rgba(59,130,246,0.30)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {isAgent ? <User size={16} /> : <Home size={16} />}
              <span>{homeLabel}</span>
            </Link>
          </div>
        </motion.div>

        {/* Small footer note */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.6 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-6 text-[10px] font-extrabold text-[var(--text-faint)] tracking-widest uppercase"
        >
          Saudi German Health · PMS Dashboard
        </motion.p>
      </div>
    </div>
  );
};

export default NotFound;
