import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { User, Mail, Lock, Eye, EyeOff, ArrowRight, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

export const RegisterPage: React.FC = () => {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessNotice(null);

    if (!fullName.trim()) {
      setError('Please provide your full name.');
      return;
    }
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const res = await register(email, password, fullName);
      if (res.error) {
        setError(res.error);
      } else if (res.confirmationRequired) {
        setSuccessNotice(
          'Account created successfully! Please check your email inbox to confirm your account before signing in.'
        );
      } else {
        navigate('/', { replace: true });
      }
    } catch {
      setError('Service temporarily unavailable. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="auth-card-title">Create Account</h2>
      <p className="auth-card-desc">Join the Company OCR Document Intelligence Platform.</p>

      {successNotice ? (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <div className="auth-alert-success" style={{ marginBottom: '20px', textAlign: 'left' }}>
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <span>{successNotice}</span>
          </div>
          <Link to="/login" className="auth-submit-btn" style={{ textDecoration: 'none' }}>
            <span>Proceed to Sign In</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      ) : (
        <>
          {error && (
            <div className="auth-alert-error" style={{ marginBottom: '18px' }} role="alert">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="auth-form" noValidate>
            {/* Full Name */}
            <div className="auth-field-group">
              <label className="auth-label" htmlFor="register-name">
                Full Name
              </label>
              <div className="auth-input-container">
                <User className="auth-input-icon" />
                <input
                  id="register-name"
                  type="text"
                  autoComplete="name"
                  autoFocus
                  className="auth-input"
                  placeholder="Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </div>

            {/* Email Field */}
            <div className="auth-field-group">
              <label className="auth-label" htmlFor="register-email">
                Email Address
              </label>
              <div className="auth-input-container">
                <Mail className="auth-input-icon" />
                <input
                  id="register-email"
                  type="email"
                  autoComplete="email"
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
              <label className="auth-label" htmlFor="register-password">
                Password
              </label>
              <div className="auth-input-container">
                <Lock className="auth-input-icon" />
                <input
                  id="register-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="auth-input"
                  placeholder="Minimum 8 characters"
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

            {/* Confirm Password Field */}
            <div className="auth-field-group">
              <label className="auth-label" htmlFor="register-confirm-password">
                Confirm Password
              </label>
              <div className="auth-input-container">
                <Lock className="auth-input-icon" />
                <input
                  id="register-confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="auth-input"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </div>

            {/* Submit Button */}
            <button type="submit" className="auth-submit-btn" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Creating Account...</span>
                </>
              ) : (
                <>
                  <span>Create Account</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Footer */}
          <div className="auth-card-footer">
            Already have an account?{' '}
            <Link to="/login" className="auth-link" style={{ fontWeight: 600 }}>
              Sign in
            </Link>
          </div>
        </>
      )}
    </div>
  );
};

export default RegisterPage;
