import { AlertTriangle, CheckCircle2, FileText, Loader2, Search, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { getErrorMessage } from "../services/api";
import type { ChunkInfo, DocumentInfo, SearchHit } from "../types";

interface Props {
  documents: DocumentInfo[];
  canManage: boolean;
  onUpload: (file: File, meta: { source_name: string; source_type: string }) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onSearch: (query: string) => Promise<SearchHit[]>;
  onPreview: (id: string) => Promise<ChunkInfo[]>;
}

const TYPE_SUGGESTIONS = ["official documentation", "blog", "encyclopedia", "report", "uploaded document"];

export default function DocumentsPanel({ documents, canManage, onUpload, onDelete, onSearch, onPreview }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [sourceName, setSourceName] = useState("");
  const [sourceType, setSourceType] = useState("uploaded document");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [preview, setPreview] = useState<{ id: string; chunks: ChunkInfo[] } | null>(null);

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await onUpload(file, { source_name: sourceName || "Uploaded document", source_type: sourceType });
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const runSearch = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSearching(true);
    try {
      setHits(await onSearch(query));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSearching(false);
    }
  };

  const togglePreview = async (id: string) => {
    if (preview?.id === id) return setPreview(null);
    try {
      setPreview({ id, chunks: await onPreview(id) });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <FileText className="h-4 w-4 text-slate-500" /> Documents ({documents.length})
      </h2>
      {error && <div role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {canManage && (
        <form onSubmit={upload} className="mb-4 space-y-2">
          <input ref={fileRef} type="file" required accept=".pdf,.txt,.md,.markdown,.docx"
            className="block w-full text-xs text-slate-600 file:mr-2 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-semibold" />
          <input className="input !py-1.5 text-xs" placeholder="Source name (e.g. Amazon Web Services)"
            value={sourceName} maxLength={120} onChange={(e) => setSourceName(e.target.value)} />
          <input className="input !py-1.5 text-xs" list="source-types" placeholder="Source type"
            value={sourceType} maxLength={60} onChange={(e) => setSourceType(e.target.value)} />
          <datalist id="source-types">{TYPE_SUGGESTIONS.map((t) => <option key={t} value={t} />)}</datalist>
          <button type="submit" disabled={uploading} className="btn-primary w-full !py-1.5 text-xs">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload
          </button>
          <p className="text-xs text-slate-500">PDF, DOCX, TXT or Markdown, up to 10 MB. Constraints apply to the source name and type.</p>
        </form>
      )}

      {documents.length === 0 ? (
        <p className="text-sm text-slate-500">No documents yet.</p>
      ) : (
        <ul className="space-y-2">
          {documents.map((d) => (
            <li key={d.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <div className="flex items-start justify-between gap-2">
                <button className="min-w-0 text-left" onClick={() => d.status === "READY" && togglePreview(d.id)}>
                  <p className="truncate font-medium">{d.title}</p>
                  <p className="truncate text-xs text-slate-500">{d.source_name} · {d.source_type}</p>
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  {d.status === "PROCESSING" && <Loader2 className="h-4 w-4 animate-spin text-brand-600" aria-label="Processing" />}
                  {d.status === "READY" && <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-label="Ready" />}
                  {d.status === "FAILED" && <AlertTriangle className="h-4 w-4 text-red-600" aria-label="Failed" />}
                  {canManage && (
                    <button onClick={() => onDelete(d.id)} className="text-slate-400 hover:text-red-600" aria-label={`Delete ${d.title}`}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
              {d.status === "READY" && (
                <p className="mt-1 text-xs text-slate-400">
                  {d.chunk_count} chunks{d.page_count ? ` · ${d.page_count} pages` : ""} · {d.embedding_backend}
                  {d.flagged_chunks > 0 && <span className="ml-1 text-amber-700">· {d.flagged_chunks} suspicious chunk(s) excluded</span>}
                </p>
              )}
              {d.status === "FAILED" && d.error && <p className="mt-1 text-xs text-red-700">{d.error}</p>}
              {preview?.id === d.id && (
                <ul className="mt-2 space-y-1 border-t border-slate-200 pt-2">
                  {preview.chunks.map((c) => (
                    <li key={c.id} className="line-clamp-3 text-xs text-slate-600">
                      {c.page ? `p.${c.page}: ` : ""}{c.text}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={runSearch} className="mt-4 flex gap-2">
        <input className="input !py-1.5 text-xs" placeholder="Search the documents…" value={query}
          minLength={2} maxLength={500} onChange={(e) => setQuery(e.target.value)} aria-label="Search documents" />
        <button type="submit" disabled={searching || query.trim().length < 2} className="btn-secondary !px-2.5 !py-1.5" aria-label="Search">
          {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </button>
      </form>
      {hits && (
        <ul className="mt-3 space-y-2">
          {hits.length === 0 && <li className="text-sm text-slate-500">No matching passages (excluded sources are never shown).</li>}
          {hits.map((h) => (
            <li key={h.chunk_id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs">
              <p className="font-medium text-slate-800">
                {h.title}{h.page ? ` · p.${h.page}` : ""}
                <span className="ml-2 text-slate-400">score {h.score.toFixed(2)}</span>
                {h.preferred && <span className="ml-2 font-semibold uppercase text-emerald-700">preferred</span>}
              </p>
              <p className="mt-1 line-clamp-3 text-slate-600">{h.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}