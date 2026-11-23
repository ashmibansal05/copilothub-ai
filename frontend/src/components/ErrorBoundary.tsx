import { AlertTriangle } from "lucide-react";
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface State {
  failed: boolean;
}

/** Catches rendering crashes so the user sees a helpful screen instead of a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" aria-hidden />
          <h1 className="mt-3 text-xl font-bold">Something went wrong</h1>
          <p className="mt-1 text-sm text-slate-600">The page hit an unexpected error. Your data is safe on the server.</p>
          <button className="btn-primary mt-4" onClick={() => window.location.assign("/dashboard")}>
            Back to the dashboard
          </button>
        </div>
      </div>
    );
  }
}