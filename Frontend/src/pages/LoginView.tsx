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
    <main className="login-shell">
      <div className="login-network login-network--left" aria-hidden="true">
        <span className="login-network__node login-network__node--one" />
        <span className="login-network__node login-network__node--two" />
        <span className="login-network__node login-network__node--three" />
      </div>
      <div className="login-network login-network--right" aria-hidden="true">
        <span className="login-network__node login-network__node--one" />
        <span className="login-network__node login-network__node--two" />
        <span className="login-network__node login-network__node--three" />
      </div>
      <div className="login-orb login-orb--blue" aria-hidden="true" />
      <div className="login-orb login-orb--violet" aria-hidden="true" />

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="login-card"
      >
        <div className="login-card__shine" aria-hidden="true" />
        <div className="login-card__content">
        {/* App Logo */}
        <div className="login-brand">
          <div className="login-brand__mark">
            <HeartPulse size={34} strokeWidth={2.2} aria-hidden="true" />
          </div>
          <h1>SGH Hub</h1>
          <p>Intelligence Portal</p>
        </div>

        {/* Error Message banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="login-alert"
            role="alert"
          >
            <AlertCircle size={20} aria-hidden="true" />
            <span>{error}</span>
          </motion.div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="login-form">
          {/* Username Field */}
          <div className="login-field-group">
            <label htmlFor="login-username">Username</label>
            <div className="login-field">
              <span className="login-field__icon" aria-hidden="true">
                <User size={20} />
              </span>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); setError(null); setUsernameError(null); }}
                placeholder="Enter username"
                autoComplete="username"
                aria-invalid={Boolean(usernameError)}
                aria-describedby={usernameError ? 'login-username-error' : undefined}
                disabled={isLoading}
              />
              {usernameError && (
                <span id="login-username-error" className="login-field__error">{usernameError}</span>
              )}
            </div>
          </div>

          {/* Password Field */}
          <div className="login-field-group">
            <label htmlFor="login-password">Password</label>
            <div className="login-field">
              <span className="login-field__icon" aria-hidden="true">
                <Lock size={20} />
              </span>
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(null); setPasswordError(null); }}
                placeholder="Enter password"
                autoComplete="current-password"
                aria-invalid={Boolean(passwordError)}
                aria-describedby={passwordError ? 'login-password-error' : undefined}
                disabled={isLoading}
              />
              {passwordError && (
                <span id="login-password-error" className="login-field__error">{passwordError}</span>
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

          {/* Submit Button */}
          <button
            id="btn-login-submit"
            type="submit"
            disabled={isLoading}
            className="login-submit"
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
        <p className="login-security-note">Secure access to your performance intelligence workspace</p>
        </div>
      </motion.div>
    </main>
  );
};

export default LoginView;
