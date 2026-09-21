import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary caught error]:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  private handleDismiss = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          className="error-boundary-container"
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            backgroundColor: 'var(--bg-main, #0f172a)',
            color: 'var(--text-main, #f8fafc)',
            fontFamily: 'var(--font-sans, system-ui, -apple-system, sans-serif)',
          }}
        >
          <div
            style={{
              maxWidth: '600px',
              width: '100%',
              backgroundColor: 'var(--bg-surface, #1e293b)',
              border: '1px solid var(--border-color, rgba(255, 255, 255, 0.1))',
              borderRadius: '12px',
              padding: '2rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
              <div
                style={{
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  color: '#ef4444',
                  padding: '0.75rem',
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <AlertTriangle size={28} />
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>Application Error Encountered</h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-muted, #94a3b8)' }}>
                  A runtime render error was caught and prevented a blank screen.
                </p>
              </div>
            </div>

            <div
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.3)',
                borderRadius: '8px',
                padding: '1rem',
                marginBottom: '1.5rem',
                border: '1px solid rgba(255, 255, 255, 0.05)',
              }}
            >
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f87171', marginBottom: '0.5rem' }}>
                {this.state.error?.name || 'Error'}: {this.state.error?.message || 'Unknown error occurred'}
              </div>
              {this.state.error?.stack && (
                <pre
                  style={{
                    margin: 0,
                    fontSize: '0.75rem',
                    color: 'var(--text-muted, #94a3b8)',
                    maxHeight: '160px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    fontFamily: 'monospace',
                  }}
                >
                  {this.state.error.stack}
                </pre>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={this.handleDismiss}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color, rgba(255, 255, 255, 0.2))',
                  backgroundColor: 'transparent',
                  color: 'var(--text-main, #f8fafc)',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  fontSize: '0.875rem',
                }}
              >
                <Home size={15} />
                <span>Dismiss</span>
              </button>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                }}
              >
                <RefreshCw size={15} />
                <span>Reload Application</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
