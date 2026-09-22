import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Mail, ArrowLeft, ArrowRight, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { resetPassword } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError('Please provide your email address.');
      return;
    }

    setLoading(true);
    try {
      const res = await resetPassword(email);
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess(true);
      }
    } catch {
      setError('Service temporarily unavailable. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="auth-card-title">Reset Password</h2>
      <p className="auth-card-desc">Enter your email address and we will send you a recovery link.</p>

      {success ? (
        <div style={{ textAlign: 'center', padding: '10px 0' }}>
          <div className="auth-alert-success" style={{ marginBottom: '20px', textAlign: 'left' }}>
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <span>
              If an account exists for <strong style={{ color: '#FFFFFF' }}>{email}</strong>, password reset instructions have been dispatched.
            </span>
          </div>
          <Link to="/login" className="auth-submit-btn" style={{ textDecoration: 'none' }}>
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Sign In</span>
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
              <label className="auth-label" htmlFor="forgot-email">
                Email Address
              </label>
              <div className="auth-input-container">
                <Mail className="auth-input-icon" />
                <input
                  id="forgot-email"
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

            <button type="submit" className="auth-submit-btn" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending Link...</span>
                </>
              ) : (
                <>
                  <span>Send Recovery Link</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="auth-card-footer">
            Remember your password?{' '}
            <Link to="/login" className="auth-link" style={{ fontWeight: 600 }}>
              Back to sign in
            </Link>
          </div>
        </>
      )}
    </div>
  );
};

export default ForgotPasswordPage;
