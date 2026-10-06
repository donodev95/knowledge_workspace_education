"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paper, useWorkspace } from "@/store/workspace";
type Document = {
  id: string;
  display_name: string;
  original_filename: string;
  status: string;
};
export function Documents() {
  const { session, papers, selectedPaperId, setPapers, selectPaper } =
    useWorkspace();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    api<Paper[]>("/papers", session!.token)
      .then((items) => {
        if (!cancelled) setPapers(items);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, setPapers]);
  useEffect(() => {
    let cancelled = false;
    if (selectedPaperId)
      api<Document[]>(`/documents?paper_id=${selectedPaperId}`, session!.token)
        .then((items) => {
          if (!cancelled) setDocuments(items);
        })
        .catch((e) => {
          if (!cancelled) setError(e.message);
        });
    return () => {
      cancelled = true;
    };
  }, [selectedPaperId, session]);
  return (
    <main className="dashboard">
      <div className="dashboard-heading">
        <div>
          <span className="eyebrow">YOUR RESEARCH, IN ONE PLACE</span>
          <h1>Library</h1>
          <p>Build the foundation for your next conversation.</p>
        </div>
        <span className="paper-count">
          {papers.length} {papers.length === 1 ? "paper" : "papers"}
        </span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <div className="dashboard-grid">
        <CreatePaper
          onCreated={(paper) => {
            setPapers([...papers, paper]);
            selectPaper(paper.id);
            setDocuments([]);
            setNotice("Paper created. You can now upload its documents.");
          }}
          onError={setError}
        />
        <section className="panel">
          <div className="panel-number">02</div>
          <h2>Select a paper</h2>
          <p>Choose where your documents belong.</p>
          <SelectPaper
            papers={papers}
            value={selectedPaperId}
            loading={loading}
            onChange={(id) => {
              selectPaper(id);
              setDocuments([]);
              setError("");
              setNotice("");
            }}
          />
          {selectedPaperId && (
            <div className="selected-paper">
              <span>▤</span>
              <strong>
                {papers.find((p) => p.id === selectedPaperId)?.title}
              </strong>
            </div>
          )}
        </section>
        <UploadDocument
          paperId={selectedPaperId}
          onError={setError}
          onUploaded={(document, warning) => {
            setDocuments((items) => [...items, document]);
            setNotice(
              warning
                ? `Document uploaded. Embedding needs attention: ${warning}`
                : "Document uploaded successfully.",
            );
          }}
        />
      </div>
      <section className="document-section">
        <h2>
          Documents <span>{documents.length}</span>
        </h2>
        {!selectedPaperId ? (
          <p>Select a paper to view its documents.</p>
        ) : documents.length === 0 ? (
          <div className="document-empty">
            No documents yet. Upload a component overview, assessment brief, or
            rubric.
          </div>
        ) : (
          <ul className="document-list">
            {documents.map((doc) => (
              <li key={doc.id}>
                <span>▤</span>
                <strong>{doc.display_name || doc.original_filename}</strong>
                <span className="document-status">
                  {doc.status.replaceAll("_", " ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
export function CreatePaper({
  onCreated,
  onError,
}: {
  onCreated: (paper: Paper) => void;
  onError: (error: string) => void;
}) {
  const token = useWorkspace((s) => s.session!.token);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    onError("");
    try {
      const paper = await api<Paper>("/papers", token, {
        method: "POST",
        body: JSON.stringify({
          code: String(data.get("code")).trim(),
          title: String(data.get("title")).trim(),
        }),
      });
      onCreated(paper);
      form.reset();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unable to create paper");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="panel-number">01</div>
      <h2>Create a new paper</h2>
      <p>A home for a subject and its sources.</p>
      <form onSubmit={submit}>
        <label>
          Paper code
          <input
            name="code"
            placeholder="e.g. COMP101"
            required
            maxLength={100}
            pattern={".*\\S.*"}
          />
        </label>
        <label>
          Paper title
          <input
            name="title"
            placeholder="e.g. Introduction to Computing"
            required
            maxLength={500}
            pattern={".*\\S.*"}
          />
        </label>
        <button className="secondary" disabled={busy}>
          {busy ? "Creating…" : "＋ Create paper"}
        </button>
      </form>
    </section>
  );
}
export function SelectPaper({
  papers,
  value,
  loading,
  onChange,
}: {
  papers: Paper[];
  value: string;
  loading: boolean;
  onChange: (id: string) => void;
}) {
  return (
    <label>
      Paper
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={loading}
      >
        <option value="">
          {loading ? "Loading papers…" : "Choose a paper"}
        </option>
        {papers.map((p) => (
          <option key={p.id} value={p.id}>
            {p.code} — {p.title}
          </option>
        ))}
      </select>
    </label>
  );
}
export function UploadFile({
  onChange,
  disabled,
}: {
  onChange: (file: File | null) => void;
  disabled: boolean;
}) {
  return (
    <label className="file-picker">
      <span>↑</span>
      <strong>Choose a document</strong>
      <small>PDF, DOCX, or text file</small>
      <input
        type="file"
        name="file"
        required
        disabled={disabled}
        accept=".pdf,.docx,.txt,.md"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}
export function UploadDocument({
  paperId,
  onUploaded,
  onError,
}: {
  paperId: string;
  onUploaded: (doc: Document, warning: string | null) => void;
  onError: (error: string) => void;
}) {
  const token = useWorkspace((s) => s.session!.token);
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState("component_overview");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!paperId || !file) return;
    const form = e.currentTarget;
    const data = new FormData(form);
    data.set("paper_id", paperId);
    data.set("document_type", type);
    data.set("embed", "true");
    if (type === "component_overview") data.delete("assessment_number");
    setBusy(true);
    onError("");
    try {
      const result = await api<{
        source_document: Document;
        embedding_error: string | null;
      }>("/documents/upload", token, { method: "POST", body: data });
      onUploaded(result.source_document, result.embedding_error);
      form.reset();
      setType("component_overview");
      setFile(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unable to upload document");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="panel-number">03</div>
      <h2>Upload a document</h2>
      <p>Give your questions something to draw on.</p>
      <form onSubmit={submit}>
        <fieldset disabled={!paperId || busy}>
          <label>
            Document type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="component_overview">Component overview</option>
              <option value="assessment_brief">Assessment brief</option>
              <option value="rubric">Rubric</option>
            </select>
          </label>
          {type !== "component_overview" && (
            <label>
              Assessment number
              <input name="assessment_number" type="number" min={1} required />
            </label>
          )}
          <UploadFile disabled={!paperId || busy} onChange={setFile} />
          {file && <p className="file-name">{file.name}</p>}
          <button className="primary" disabled={!paperId || !file || busy}>
            {busy ? "Uploading…" : "Upload document ↑"}
          </button>
        </fieldset>
      </form>
    </section>
  );
}
