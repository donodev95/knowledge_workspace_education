"use client";

import {
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  CircleUserRound,
  FileUp,
  Files,
  FolderOpen,
  LogOut,
  Menu,
  MessageCircle,
  MessageSquarePlus,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type AuthMode = "login" | "register";
type DocumentType = "component_overview" | "assessment_brief" | "rubric";
type Paper = { id: string; code: string; title: string };
type SourceDocument = {
  id: string;
  original_filename: string;
  document_type: DocumentType;
  assessment_number: number | null;
  status: string;
  created_at: string;
};

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(
      body?.message ??
        body?.detail ??
        "Something went wrong. Please try again.",
    );
  return body as T;
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");

  useEffect(() => {
    setToken(window.localStorage.getItem("knowledge_token"));
    setEmail(window.localStorage.getItem("knowledge_email") ?? "");
  }, []);

  function signOut() {
    window.localStorage.removeItem("knowledge_token");
    window.localStorage.removeItem("knowledge_email");
    setToken(null);
    setEmail("");
  }

  async function handleAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    setAuthNotice("");
    const form = new FormData(event.currentTarget);
    const payload = {
      email: String(form.get("email")),
      password: String(form.get("password")),
      ...(authMode === "register"
        ? { username: String(form.get("username")) }
        : {}),
    };
    try {
      if (authMode === "register") {
        await request("/auth/register", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setAuthMode("login");
        setAuthNotice("Your account is ready. Sign in to open your workspace.");
      } else {
        const result = await request<{ access_token: string }>("/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: payload.email,
            password: payload.password,
          }),
        });
        window.localStorage.setItem("knowledge_token", result.access_token);
        window.localStorage.setItem("knowledge_email", payload.email);
        setToken(result.access_token);
        setEmail(payload.email);
      }
    } catch (error) {
      setAuthError(
        error instanceof Error ? error.message : "Unable to authenticate.",
      );
    } finally {
      setAuthBusy(false);
    }
  }

  if (!token)
    return (
      <AuthScreen
        mode={authMode}
        busy={authBusy}
        error={authError}
        notice={authNotice}
        onModeChange={(mode) => {
          setAuthMode(mode);
          setAuthError("");
          setAuthNotice("");
        }}
        onSubmit={handleAuth}
      />
    );
  return <Dashboard token={token} email={email} onSignOut={signOut} />;
}

function AuthScreen({
  mode,
  busy,
  error,
  notice,
  onModeChange,
  onSubmit,
}: {
  mode: AuthMode;
  busy: boolean;
  error: string;
  notice: string;
  onModeChange: (mode: AuthMode) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="brand-mark">
          <Sparkles size={16} /> KNOWLEDGE / WORKSPACE
        </div>
        <div className="story-copy">
          <p className="eyebrow">A calmer home for your source material</p>
          <h1>
            Make every document
            <br />
            <em>count twice.</em>
          </h1>
          <p className="story-text">
            Bring papers, briefs, and rubrics into one considered workspace.
            Extract the signal once, then use it everywhere.
          </p>
        </div>
        <div className="story-footer">
          <ShieldCheck size={16} />
          <span>Private by default · Built for careful work</span>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="mobile-brand brand-mark">
            <Sparkles size={16} /> KNOWLEDGE / WORKSPACE
          </div>
          <div className="auth-heading">
            <p className="eyebrow">
              {mode === "login" ? "Welcome back" : "Start a workspace"}
            </p>
            <h2>
              {mode === "login" ? "Sign in to continue" : "Create your account"}
            </h2>
            <p>
              {mode === "login"
                ? "Your sources are waiting."
                : "A clear place for the work ahead."}
            </p>
          </div>
          <div className="auth-tabs" role="tablist">
            <button
              className={mode === "login" ? "active" : ""}
              onClick={() => onModeChange("login")}
            >
              Log in
            </button>
            <button
              className={mode === "register" ? "active" : ""}
              onClick={() => onModeChange("register")}
            >
              Register
            </button>
          </div>
          <form className="auth-form" onSubmit={onSubmit}>
            {mode === "register" && (
              <label>
                Username
                <input
                  name="username"
                  placeholder="your-name"
                  autoComplete="username"
                  required
                />
              </label>
            )}
            <label>
              Email address
              <input
                name="email"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                placeholder="At least 8 characters"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                minLength={8}
                required
              />
            </label>
            {error && (
              <p className="form-message error">
                <X size={15} />
                {error}
              </p>
            )}
            {notice && (
              <p className="form-message success">
                <Check size={15} />
                {notice}
              </p>
            )}
            <button className="primary-button" disabled={busy}>
              {busy
                ? "Working..."
                : mode === "login"
                  ? "Open workspace"
                  : "Create workspace"}
              <ArrowUpRight size={17} />
            </button>
          </form>
          <p className="auth-note">
            By continuing, you agree to keep your workspace focused and your
            credentials private.
          </p>
        </div>
      </section>
    </main>
  );
}

function Dashboard({
  token,
  email,
  onSignOut,
}: {
  token: string;
  email: string;
  onSignOut: () => void;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [selectedPaper, setSelectedPaper] = useState("");
  const [documentType, setDocumentType] =
    useState<DocumentType>("component_overview");
  const [assessmentNumber, setAssessmentNumber] = useState("1");
  const [file, setFile] = useState<File | null>(null);
  const [paperCode, setPaperCode] = useState("");
  const [paperTitle, setPaperTitle] = useState("");
  const [showNewPaper, setShowNewPaper] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadPapers() {
    const result = await request<Paper[]>("/papers", {}, token);
    setPapers(result);
    setSelectedPaper((current) => current || result[0]?.id || "");
  }
  async function loadDocuments(paperId: string) {
    if (!paperId) return setDocuments([]);
    setDocuments(
      await request<SourceDocument[]>(
        `/documents?paper_id=${paperId}`,
        {},
        token,
      ),
    );
  }
  useEffect(() => {
    loadPapers().catch((err) => setError(err.message));
  }, []);
  useEffect(() => {
    loadDocuments(selectedPaper).catch((err) => setError(err.message));
  }, [selectedPaper]);

  async function createPaper() {
    setBusy(true);
    setError("");
    try {
      const paper = await request<Paper>(
        "/papers",
        {
          method: "POST",
          body: JSON.stringify({ code: paperCode, title: paperTitle }),
        },
        token,
      );
      setPapers((current) => [...current, paper]);
      setSelectedPaper(paper.id);
      setPaperCode("");
      setPaperTitle("");
      setShowNewPaper(false);
      setMessage("Paper created. You can upload its first source now.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create paper.");
    } finally {
      setBusy(false);
    }
  }
  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPaper)
      return setError(
        "Select a paper before uploading. Every document must belong to a paper.",
      );
    if (!file) return setError("Choose a file before uploading.");
    setBusy(true);
    setError("");
    setMessage("");
    const form = new FormData();
    form.append("file", file);
    form.append("paper_id", selectedPaper);
    form.append("document_type", documentType);
    form.append("embed", "true");
    if (documentType !== "component_overview")
      form.append("assessment_number", assessmentNumber);
    try {
      await request("/documents/upload", { method: "POST", body: form }, token);
      setFile(null);
      setMessage("Upload received. Extraction is now being prepared.");
      await loadDocuments(selectedPaper);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not upload document.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-top">
          <div className="brand-mark">
            <Sparkles size={16} /> KNOWLEDGE / WORKSPACE
          </div>
          <button
            className="icon-button mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-label">Workspace</div>
        <nav>
          <Link className="nav-item active" href="/chat">
            <MessageSquarePlus size={18} />
            <span>New chat</span>
            <span className="nav-dot" />
          </Link>
          <div className="sidebar-section-label">Conversations</div>
          <div className="conversation-list">
            <Link className="conversation-item" href="/chat">
              <MessageCircle size={15} />
              <span>Untitled conversation</span>
            </Link>
            <Link className="conversation-item" href="/chat">
              <MessageCircle size={15} />
              <span>Research notes</span>
            </Link>
          </div>
          <Link className="nav-item" href="/">
            <Files size={18} />
            <span>Source library</span>
          </Link>
          <button className="nav-item">
            <BookOpen size={18} />
            <span>Coverage analysis</span>
            <span className="soon">Soon</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="status-line">
            <span className="status-pulse" /> API connected
          </div>
          <div className="version">Workspace 0.1 · private beta</div>
        </div>
      </aside>
      <section className="main-area">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={21} />
          </button>
          <div className="topbar-context">
            <span className="crumb-muted">Workspace</span>
            <span>/</span>
            <strong>Upload document</strong>
          </div>
          <div className="account-menu">
            <div className="account-avatar">
              <CircleUserRound size={18} />
            </div>
            <span className="account-email">{email}</span>
            <ChevronDown size={15} />
            <button
              className="logout-button"
              onClick={onSignOut}
              title="Log out"
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <div className="content-wrap">
          <div className="page-intro">
            <div>
              <p className="eyebrow">Source library</p>
              <h1>Bring the context in.</h1>
              <p>
                Upload a source document and we&apos;ll prepare it for analysis.
              </p>
            </div>
            <div className="intro-mark">
              <FileUp size={24} />
              <span>01</span>
            </div>
          </div>
          <div className="workspace-grid">
            <section className="upload-card">
              <div className="section-heading">
                <div>
                  <span className="step-number">01</span>
                  <h2>Upload a source</h2>
                </div>
                <span className="required-label">Required fields</span>
              </div>
              <form onSubmit={uploadDocument} className="upload-form">
                <label className="field-label">
                  Paper
                  <select
                    value={selectedPaper}
                    onChange={(event) => setSelectedPaper(event.target.value)}
                  >
                    <option value="">
                      {papers.length
                        ? "Select a paper"
                        : "Create a paper first"}
                    </option>
                    {papers.map((paper) => (
                      <option key={paper.id} value={paper.id}>
                        {paper.code} · {paper.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setShowNewPaper((value) => !value)}
                >
                  <Plus size={15} /> Create a new paper
                </button>
                {showNewPaper && (
                  <div className="new-paper-form">
                    <input
                      value={paperCode}
                      onChange={(event) => setPaperCode(event.target.value)}
                      placeholder="Paper code"
                      required
                    />
                    <input
                      value={paperTitle}
                      onChange={(event) => setPaperTitle(event.target.value)}
                      placeholder="Paper title"
                      required
                    />
                    <button
                      type="button"
                      className="small-button"
                      disabled={busy || !paperCode || !paperTitle}
                      onClick={createPaper}
                    >
                      Save paper
                    </button>
                  </div>
                )}
                <div className="field-row">
                  <label className="field-label">
                    Document type
                    <select
                      value={documentType}
                      onChange={(event) =>
                        setDocumentType(event.target.value as DocumentType)
                      }
                    >
                      <option value="component_overview">
                        Component overview
                      </option>
                      <option value="assessment_brief">Assessment brief</option>
                      <option value="rubric">Rubric</option>
                    </select>
                  </label>
                  {documentType !== "component_overview" && (
                    <label className="field-label">
                      Assessment number
                      <input
                        type="number"
                        min="1"
                        value={assessmentNumber}
                        onChange={(event) =>
                          setAssessmentNumber(event.target.value)
                        }
                      />
                    </label>
                  )}
                </div>
                <label className={`dropzone ${file ? "has-file" : ""}`}>
                  <input
                    type="file"
                    accept=".pdf,.doc,.docx,.txt"
                    onChange={(event) =>
                      setFile(event.target.files?.[0] ?? null)
                    }
                  />
                  {file ? (
                    <>
                      <Check className="drop-icon" size={28} />
                      <strong>{file.name}</strong>
                      <span>
                        {(file.size / 1024 / 1024).toFixed(2)} MB · Ready to
                        upload
                      </span>
                    </>
                  ) : (
                    <>
                      <FolderOpen className="drop-icon" size={28} />
                      <strong>Drop a file here or browse</strong>
                      <span>
                        PDF, DOCX, or TXT · up to your configured limit
                      </span>
                    </>
                  )}
                </label>
                {error && (
                  <p className="form-message error">
                    <X size={15} />
                    {error}
                  </p>
                )}
                {message && (
                  <p className="form-message success">
                    <Check size={15} />
                    {message}
                  </p>
                )}
                <button
                  className="primary-button upload-button"
                  disabled={busy}
                >
                  {busy ? "Uploading..." : "Upload document"}
                  <ArrowUpRight size={17} />
                </button>
              </form>
            </section>
            <aside className="library-card">
              <div className="section-heading">
                <div>
                  <span className="step-number">02</span>
                  <h2>Your library</h2>
                </div>
                <button
                  className="icon-button"
                  onClick={() => loadDocuments(selectedPaper)}
                  title="Refresh documents"
                >
                  <RefreshCw size={16} />
                </button>
              </div>
              {!selectedPaper ? (
                <div className="empty-state">
                  <BookOpen size={22} />
                  <p>Choose a paper to see its source library.</p>
                </div>
              ) : documents.length === 0 ? (
                <div className="empty-state">
                  <Files size={22} />
                  <p>No documents yet. Your first upload will appear here.</p>
                </div>
              ) : (
                <div className="document-list">
                  {documents.map((document) => (
                    <div className="document-row" key={document.id}>
                      <div className="document-icon">
                        <Files size={17} />
                      </div>
                      <div className="document-meta">
                        <strong>{document.original_filename}</strong>
                        <span>
                          {document.document_type.replaceAll("_", " ")}
                          {document.assessment_number
                            ? ` · assessment ${document.assessment_number}`
                            : ""}
                        </span>
                      </div>
                      <span className={`document-status ${document.status}`}>
                        {document.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          </div>
        </div>
      </section>
    </main>
  );
}
