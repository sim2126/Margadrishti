import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  label?: string;
}
interface State {
  error: Error | null;
}

/** Stops a render-time error from white-screening the app. Scope it around the whole app
 *  and around volatile panels (the map) so one failure degrades gracefully. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught:", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full w-full items-center justify-center p-6">
          <div className="max-w-sm rounded-[--radius] border bg-[--color-surface] p-5 text-center">
            <div className="text-sm font-semibold text-[--color-fg]">
              {this.props.label ?? "Something went wrong"}
            </div>
            <p className="mt-1 text-xs text-[--color-muted]">
              This panel hit an unexpected error and was contained. The rest of the console
              keeps working.
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="mt-3 rounded-[--radius] border px-3 py-1.5 text-xs text-[--color-fg] hover:bg-[--color-surface-2]"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
