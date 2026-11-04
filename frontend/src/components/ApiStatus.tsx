import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { authService } from "../services/authService";
import type { HealthResponse } from "../types";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "error" };

export default function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    authService
      .health()
      .then((data) => setState({ kind: "ok", data }))
      .catch(() => setState({ kind: "error" }));
  }, []);

  if (state.kind === "loading")
    return (
      <span className="inline-flex items-center gap-2 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Checking backend...
      </span>
    );
  if (state.kind === "error")
    return (
      <span className="inline-flex items-center gap-2 rounded-full bg-red-50 px-3 py-1 text-sm text-red-700">
        <XCircle className="h-4 w-4" /> Backend unreachable
      </span>
    );
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-sm text-emerald-700">
      <CheckCircle2 className="h-4 w-4" /> Backend online
      {state.data.demo_mode && " · demo mode"}
    </span>
  );
}