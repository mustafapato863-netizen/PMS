import { Component, lazy, Suspense, type ErrorInfo, type ReactNode } from 'react';

const MaintenanceView = lazy(() => import('../../pages/MaintenanceView'));

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
  componentStack: string | null;
};

export class AppErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    error: null,
    componentStack: null,
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('App crashed safely:', error, errorInfo);
    this.setState({
      error,
      componentStack: errorInfo.componentStack || null,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      componentStack: null,
    });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <Suspense fallback={null}>
        <MaintenanceView
          mode="error"
          error={this.state.error}
          componentStack={this.state.componentStack}
          onRetry={this.handleReset}
          onGoHome={() => {
            window.location.href = '/executive';
          }}
        />
        </Suspense>
      );
    }

    return this.props.children;
  }
}

export default AppErrorBoundary;
