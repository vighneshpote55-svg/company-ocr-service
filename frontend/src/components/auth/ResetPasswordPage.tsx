import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Lock, Eye, EyeOff, ArrowRight, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

export const ResetPasswordPage: React.FC = () => {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { updatePassword } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!password) {
      setError('Password is required.');
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
      const res = await updatePassword(password);
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess(true);
        setTimeout(() => {
          navigate('/login', { replace: true });
        }, 2000);
      }
    } catch {
      setError('Failed to update password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="auth-card-title">Set New Password</h2>
      <p className="auth-card-desc">Choose a strong password with at least 8 characters.</p>

      {success ? (
        <div style={{ textAlign: 'center', padding: '10px 0' }}>
          <div className="auth-alert-success" style={{ marginBottom: '20px', textAlign: 'left' }}>
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <span>Password updated successfully! Redirecting to sign in...</span>
          </div>
          <Link to="/login" className="auth-submit-btn" style={{ textDecoration: 'none' }}>
            <span>Sign In Now</span>
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
            <div className="auth-field-group">
              <label className="auth-label" htmlFor="reset-new-password">
                New Password
              </label>
              <div className="auth-input-container">
                <Lock className="auth-input-icon" />
                <input
                  id="reset-new-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  autoFocus
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

            <div className="auth-field-group">
              <label className="auth-label" htmlFor="reset-confirm-password">
                Confirm New Password
              </label>
              <div className="auth-input-container">
                <Lock className="auth-input-icon" />
                <input
                  id="reset-confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="auth-input"
                  placeholder="Re-enter new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </div>

            <button type="submit" className="auth-submit-btn" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Updating Password...</span>
                </>
              ) : (
                <>
                  <span>Update Password</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="auth-card-footer">
            <Link to="/login" className="auth-link">
              Back to sign in
            </Link>
          </div>
        </>
      )}
    </div>
  );
};

export default ResetPasswordPage;
