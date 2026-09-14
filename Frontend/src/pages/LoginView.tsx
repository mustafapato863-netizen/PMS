import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Lock, User, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/auth';
import { useTheme } from '../context/ThemeContext';
import ThinkingDots from '../components/common/ThinkingDots';
import SghAnimatedLogo from '../components/common/SghAnimatedLogo';
import ThemeToggle from '../components/common/ThemeToggle';

const LoginView: React.FC = () => {
  const { login } = useAuth();
  const { theme } = useTheme();
  const isDark = theme === 'dark';
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
    <main className="login-shell">
      {/* 1. Animated Ambient Background Canvas */}
      <ThinkingDots isDark={isDark} />

      {/* 2. Ambient Color Atmosphere Orbs */}
      <div className="login-orb login-orb--cyan" aria-hidden="true" />
      <div className="login-orb login-orb--emerald" aria-hidden="true" />

      {/* 3. Top Floating Theme Switcher */}
      <div className="absolute top-5 right-5 z-20">
        <ThemeToggle variant="icon" />
      </div>

      {/* 4. Login Glass Card with Staggered Entrance and Dynamic Error Shake */}
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.96 }}
        animate={{
          opacity: 1,
          y: 0,
          scale: 1,
          x: error ? [-8, 8, -6, 6, -3, 3, 0] : 0,
        }}
        transition={{
          duration: 0.55,
          ease: [0.16, 1, 0.3, 1],
          x: { duration: 0.45, ease: 'easeInOut' },
        }}
        className="login-card"
      >
        <div className="login-card__shine" aria-hidden="true" />
        <div className="login-card__content">
          {/* SGH Interactive Animated Brand Header */}
          <SghAnimatedLogo
            size={70}
            title="SGH Hub"
            subtitle="Performance Intelligence Portal"
            className="mb-6"
          />

          {/* Animated Error Alert */}
          <AnimatePresence mode="wait">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.97 }}
                transition={{ duration: 0.2 }}
                className="login-alert"
                role="alert"
              >
                <AlertCircle size={18} aria-hidden="true" className="shrink-0 text-rose-400" />
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Login Form with Field Animations */}
          <form onSubmit={handleSubmit} className="login-form">
            {/* Username Field */}
            <div className="login-field-group">
              <label htmlFor="login-username">Username</label>
              <div className="login-field">
                <span className="login-field__icon" aria-hidden="true">
                  <User size={19} />
                </span>
                <input
                  id="login-username"
                  type="text"
                  value={username}
                  onChange={(e) => {
                    setUsername(e.target.value);
                    setError(null);
                    setUsernameError(null);
                  }}
                  placeholder="Enter username"
                  autoComplete="username"
                  aria-invalid={Boolean(usernameError)}
                  aria-describedby={usernameError ? 'login-username-error' : undefined}
                  disabled={isLoading}
                />
                {usernameError && (
                  <span id="login-username-error" className="login-field__error">
                    {usernameError}
                  </span>
                )}
              </div>
            </div>

            {/* Password Field */}
            <div className="login-field-group">
              <label htmlFor="login-password">Password</label>
              <div className="login-field">
                <span className="login-field__icon" aria-hidden="true">
                  <Lock size={19} />
                </span>
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError(null);
                    setPasswordError(null);
                  }}
                  placeholder="Enter password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={passwordError ? 'login-password-error' : undefined}
                  disabled={isLoading}
                />
                {passwordError && (
                  <span id="login-password-error" className="login-field__error">
                    {passwordError}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  disabled={isLoading}
                  className="login-field__toggle"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* Interactive Animated Submit Button */}
            <motion.button
              id="btn-login-submit"
              type="submit"
              disabled={isLoading}
              whileHover={!isLoading ? { scale: 1.015, y: -1 } : {}}
              whileTap={!isLoading ? { scale: 0.985 } : {}}
              className="login-submit relative overflow-hidden"
            >
              {isLoading ? (
                <>
                  <div className="w-5 h-5 rounded-full border-2 border-white/25 border-t-white animate-spin" />
                  <span>Signing In...</span>
                </>
              ) : (
                <span>Sign In</span>
              )}
            </motion.button>
          </form>

          <p className="login-security-note">
            Protected enterprise session · Saudi German Health
          </p>
        </div>
      </motion.div>
    </main>
  );
};

export default LoginView;
