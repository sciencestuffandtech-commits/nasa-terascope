import { Component } from "react";
import type { ReactNode } from "react";

export default class ErrorBoundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  render() {
    if (this.state.err)
      return <pre style={{ padding: 16, whiteSpace: "pre-wrap", color: "#8a1c1c" }}>{String(this.state.err.stack || this.state.err)}</pre>;
    return this.props.children;
  }
}