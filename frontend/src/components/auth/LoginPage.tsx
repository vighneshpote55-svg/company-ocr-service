import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle, Loader2 } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Redirect destination after successful login
  const from = (location.state as { from?: { pathname?: string } })?.from?.pathname || '/';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError('Please provide both your email address and password.');
      return;
    }

    setLoading(true);
    try {
      const res = await login(email, password);
      if (res.error) {
        setError(res.error);
      } else {
        navigate(from, { replace: true });
      }
    } catch {
      setError('Service temporarily unavailable. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="auth-card-title">Sign In</h2>
      <p className="auth-card-desc">Enter your credentials to access your document vault.</p>

      {error && (
        <div className="auth-alert-error" style={{ marginBottom: '18px' }} role="alert">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="auth-form" noValidate>
        {/* Email Field */}
        <div className="auth-field-group">
          <label className="auth-label" htmlFor="login-email">
            Email Address
          </label>
          <div className="auth-input-container">
            <Mail className="auth-input-icon" />
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              autoFocus
              className="auth-input"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              required
            />
          </div>
        </div>

        {/* Password Field */}
        <div className="auth-field-group">
          <div className="auth-field-header">
            <label className="auth-label" htmlFor="login-password">
              Password
            </label>
            <Link to="/forgot-password" className="auth-link">
              Forgot password?
            </Link>
          </div>
          <div className="auth-input-container">
            <Lock className="auth-input-icon" />
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              className="auth-input"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
            <button
              type="button"
              className="auth-password-toggle"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Remember Session */}
        <div className="auth-remember-row">
          <label className="auth-remember-label">
            <input
              type="checkbox"
              className="auth-remember-checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            <span>Remember session on this device</span>
          </label>
        </div>

        {/* Submit Button */}
        <button type="submit" className="auth-submit-btn" disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Authenticating...</span>
            </>
          ) : (
            <>
              <span>Sign In</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      {/* Footer */}
      <div className="auth-card-footer">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="auth-link" style={{ fontWeight: 600 }}>
          Create an account
        </Link>
      </div>
    </div>
  );
};

export default LoginPage;
