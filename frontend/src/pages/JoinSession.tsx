import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { RoleBadge } from "../components/StatusBadge";
import { getErrorMessage } from "../services/api";
import { sessionService } from "../services/sessionService";
import type { InvitePreview } from "../types";

export default function JoinSession() {
  const { code = "" } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    sessionService
      .preview(code)
      .then(setPreview)
      .catch((err) => setError(getErrorMessage(err)));
  }, [code]);

  const onJoin = async () => {
    setJoining(true);
    setError(null);
    try {
      const session = await sessionService.join(code);
      navigate(`/sessions/${session.id}`, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
      setJoining(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg">
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        {!preview && !error && (
          <div className="flex justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-brand-600" aria-label="Loading invite" />
          </div>
        )}

        {error && (
          <div>
            <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
            <Link to="/dashboard" className="btn-secondary mt-4">Back to dashboard</Link>
          </div>
        )}

        {preview && (
          <>
            <p className="text-sm text-slate-500">You've been invited to</p>
            <h1 className="mt-1 text-2xl font-bold">{preview.session_name}</h1>
            <p className="mt-2 text-sm text-slate-600">{preview.task}</p>
            <p className="mt-4 text-sm text-slate-500">
              Owner: {preview.owner_name} · {preview.already_member ? "Your role:" : "You'll join as:"}{" "}
              <RoleBadge role={preview.role} />
            </p>
            <div className="mt-6">
              {preview.already_member && preview.session_id ? (
                <Link to={`/sessions/${preview.session_id}`} className="btn-primary">Open session</Link>
              ) : (
                <button onClick={onJoin} disabled={joining} className="btn-primary">
                  {joining && <Loader2 className="h-4 w-4 animate-spin" />}
                  Join session
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}