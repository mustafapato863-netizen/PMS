import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Lock, User, Eye, EyeOff, HeartPulse, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/auth';

const LoginView: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  // Inline field errors
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    let hasError = false;
    if (!username.trim()) {
      setUsernameError('Username is required');
      hasError = true;
    } else {
      setUsernameError(null);
    }
    if (!password.trim()) {
      setPasswordError('Password is required');
      hasError = true;
    } else {
      setPasswordError(null);
    }
    if (hasError) {
      setError('Please correct the highlighted fields.');
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      const result = await login(username, password);
      if (result.success) {
        navigate('/executive', { replace: true });
      } else {
        setError(result.error || 'Invalid credentials');
      }
    } catch (err) {
      setError('An unexpected error occurred. Please try again.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950 p-4 overflow-hidden">
      {/* Background Decorative Gradients */}
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-600/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-600/10 blur-[120px] pointer-events-none" />
      <div className="absolute top-[30%] right-[20%] w-[300px] h-[300px] rounded-full bg-emerald-500/5 blur-[100px] pointer-events-none" />

      {/* Main Container */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-[440px] bg-slate-900/60 backdrop-blur-2xl border border-slate-800/80 p-8 rounded-3xl shadow-2xl relative z-10"
      >
        {/* App Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-3.5 rounded-2xl shadow-[0_8px_24px_rgba(59,130,246,0.35)] border border-blue-400/30 mb-4">
            <HeartPulse size={32} className="text-white animate-pulse" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">SGH Hub</h1>
          <p className="text-xs text-blue-400 font-bold uppercase tracking-widest mt-1">Intelligence Portal</p>
        </div>

        {/* Error Message banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 bg-red-950/40 border border-red-800/50 rounded-2xl flex items-start gap-3 text-red-300"
          >
            <AlertCircle size={20} className="shrink-0 mt-0.5" />
            <span className="text-xs font-semibold leading-relaxed">{error}</span>
          </motion.div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Username Field */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">Username</label>
            <div className="relative group">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-blue-400 transition-colors pointer-events-none">
                <User size={18} />
              </span>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); setError(null); setUsernameError(null); }}
                placeholder="Enter username"
                autoComplete="username"
                disabled={isLoading}
                className="w-full bg-slate-950/50 border border-slate-800 text-sm font-semibold text-white rounded-2xl pl-12 pr-4 py-3.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-slate-600 disabled:opacity-55"
              />
              {usernameError && (
                <span className="text-xs text-red-400 mt-1 block">{usernameError}</span>
              )}
            </div>
          </div>

          {/* Password Field */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">Password</label>
            </div>
            <div className="relative group">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-blue-400 transition-colors pointer-events-none">
                <Lock size={18} />
              </span>
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); setPasswordError(null); }}
                placeholder="Enter password"
                autoComplete="current-password"
                disabled={isLoading}
                className="w-full bg-slate-950/50 border border-slate-800 text-sm font-semibold text-white rounded-2xl pl-12 pr-12 py-3.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-slate-600 disabled:opacity-55"
              />
              {passwordError && (
                <span className="text-xs text-red-400 mt-1 block">{passwordError}</span>
              )}
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                disabled={isLoading}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors focus:outline-none"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Submit Button */}
          <button
            id="btn-login-submit"
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-2xl py-3.5 shadow-lg shadow-blue-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 disabled:pointer-events-none mt-2"
          >
            {isLoading ? (
              <>
                <div className="w-5 h-5 rounded-full border-2 border-white/20 border-t-white animate-spin" />
                <span>Signing In...</span>
              </>
            ) : (
              <span>Sign In</span>
            )}
          </button>
        </form>


      </motion.div>
    </div>
  );
};

export default LoginView;
