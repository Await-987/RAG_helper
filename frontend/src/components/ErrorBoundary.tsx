import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-dark-bg p-4">
          <div className="max-w-sm text-center">
            <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={24} className="text-red-400" />
            </div>
            <h1 className="text-lg font-medium text-white mb-2">出现问题</h1>
            <p className="text-sm text-zinc-400 mb-4">应用遇到了意外错误，请尝试刷新页面。</p>
            {this.state.error && (
              <div className="px-3 py-2 rounded-xl bg-zinc-800 mb-4 text-xs text-zinc-400 overflow-auto max-h-20">
                {this.state.error.message}
              </div>
            )}
            <div className="flex gap-2 justify-center">
              <button onClick={this.handleReset} className="btn btn-secondary flex items-center gap-2">
                <RefreshCw size={14} />
                重试
              </button>
              <button onClick={this.handleReload} className="btn btn-primary">
                刷新页面
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}