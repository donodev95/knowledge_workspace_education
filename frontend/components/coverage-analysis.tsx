"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { CoverageResult, Paper, useWorkspace } from "@/store/workspace";

type SourceDocument = {
  id: string;
  paper_id: string;
  document_type: string;
  assessment_number: number | null;
  display_name: string;
  original_filename: string;
  status: string;
};
type Result = CoverageResult & {
  outcome_count: number;
  requirement_count: number;
  confirmed_coverage: number;
  proposed_links: unknown[];
};
const readyStatuses = new Set(["extracted", "completed", "embedding_failed"]);
const documentName = (doc: SourceDocument) =>
  doc.display_name || doc.original_filename;

export function CoverageAnalysis() {
  const token = useWorkspace((s) => s.session!.token);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [paperId, setPaperId] = useState("");
  const [overviewId, setOverviewId] = useState("");
  const [assessmentId, setAssessmentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Paper[]>("/papers", token, { signal: controller.signal }),
      api<SourceDocument[]>("/documents", token, { signal: controller.signal }),
    ])
      .then(([paperRows, documentRows]) => {
        if (!controller.signal.aborted) {
          setPapers(paperRows);
          setDocuments(documentRows);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof Error ? e.message : "Unable to load documents.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      requestRef.current?.abort();
    };
  }, [token]);

  const paperDocuments = documents.filter((doc) => doc.paper_id === paperId);
  const overviews = paperDocuments.filter(
    (doc) => doc.document_type === "component_overview",
  );
  const assessments = paperDocuments.filter(
    (doc) => doc.document_type === "assessment_brief",
  );
  const assessment = assessments.find((doc) => doc.id === assessmentId);
  const canAnalyze =
    !loading && !busy && overviewId && assessment?.assessment_number;

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canAnalyze || !assessment) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const summary = await api<Result>("/source-item-links", token, {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          paper_id: paperId,
          assessment_number: assessment.assessment_number,
          overview_document_id: overviewId,
          assessment_document_id: assessmentId,
        }),
      });
      if (!controller.signal.aborted) setResult(summary);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Analysis failed. Please try again.",
        );
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <div className="coverage-workspace">
      <aside
        className="sidebar coverage-sidebar"
        aria-label="Coverage analysis settings"
      >
        <span className="eyebrow">ANALYSIS SETTINGS</span>
        <h2>Choose your sources</h2>
        <p>Compare assessment tasks with the learning outcomes for a paper.</p>
        <form onSubmit={analyze}>
          <fieldset disabled={loading || busy}>
            <label>
              Paper
              <select
                value={paperId}
                onChange={(e) => {
                  setPaperId(e.target.value);
                  setOverviewId("");
                  setAssessmentId("");
                  setResult(null);
                  setError("");
                }}
              >
                <option value="">
                  {loading ? "Loading papers…" : "Choose a paper"}
                </option>
                {papers.map((paper) => (
                  <option key={paper.id} value={paper.id}>
                    {paper.code} — {paper.title}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="coverage-document-options" disabled={!paperId}>
              <legend>Learning outcome document</legend>
              <p className="coverage-selection-hint">
                {!paperId
                  ? "Select a paper first."
                  : "Choose one component overview."}
              </p>
              {overviews.map((doc) => (
                <label className="coverage-document-option" key={doc.id}>
                  <input
                    type="checkbox"
                    checked={overviewId === doc.id}
                    disabled={!readyStatuses.has(doc.status)}
                    onChange={(e) => {
                      setOverviewId(e.target.checked ? doc.id : "");
                      setResult(null);
                    }}
                  />
                  <span>
                    {documentName(doc)}
                    {!readyStatuses.has(doc.status) ? " (not ready)" : ""}
                  </span>
                </label>
              ))}
              {paperId && overviews.length === 0 && (
                <p className="coverage-selection-hint">
                  No learning outcome documents uploaded.
                </p>
              )}
            </fieldset>
            <fieldset className="coverage-document-options" disabled={!paperId}>
              <legend>Task assessment document</legend>
              <p className="coverage-selection-hint">
                {!paperId
                  ? "Select a paper first."
                  : "Choose one assessment brief."}
              </p>
              {assessments.map((doc) => (
                <label className="coverage-document-option" key={doc.id}>
                  <input
                    type="checkbox"
                    checked={assessmentId === doc.id}
                    disabled={
                      !readyStatuses.has(doc.status) || !doc.assessment_number
                    }
                    onChange={(e) => {
                      setAssessmentId(e.target.checked ? doc.id : "");
                      setResult(null);
                    }}
                  />
                  <span>
                    Assessment {doc.assessment_number} — {documentName(doc)}
                    {!readyStatuses.has(doc.status) ? " (not ready)" : ""}
                  </span>
                </label>
              ))}
              {paperId && assessments.length === 0 && (
                <p className="coverage-selection-hint">
                  No assessment briefs uploaded.
                </p>
              )}
            </fieldset>
            <button className="primary" disabled={!canAnalyze}>
              {busy ? "Analysing…" : "Perform analysis →"}
            </button>
          </fieldset>
        </form>
        <Link href="/documents" className="sidebar-library">
          Upload or manage documents →
        </Link>
      </aside>
      <main className="coverage-main" aria-busy={busy}>
        <div className="dashboard-heading">
          <div>
            <h2>Coverage Analysis</h2>
            <p>See how assessment tasks address your learning outcomes.</p>
          </div>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p role="status">Loading your papers and documents…</p>
        ) : busy ? (
          <div className="document-empty" role="status">
            Analysing assessment tasks against learning outcomes. This may take
            several minutes.
          </div>
        ) : result ? (
          <section className="coverage-results" aria-label="Analysis results">
            <div className="coverage-metrics">
              <div className="panel">
                <strong>{result.outcome_count}</strong>
                <span>Learning outcomes</span>
              </div>
              <div className="panel">
                <strong>{result.requirement_count}</strong>
                <span>Assessment requirements</span>
              </div>
              <div className="panel">
                <strong>{result.proposed_links.length}</strong>
                <span>Proposed mappings</span>
              </div>
              <div className="panel">
                <strong>{Math.round(result.confirmed_coverage * 100)}%</strong>
                <span>Confirmed coverage</span>
              </div>
            </div>
            {result.outcome_reviews.map((outcome) => (
              <details key={outcome.learning_outcome.id}>
                <summary>
                  {outcome.learning_outcome.label || "Learning outcome"}:{" "}
                  {outcome.learning_outcome.content}
                </summary>
                {outcome.pairs.length === 0 && (
                  <p>No assessment pairs returned for this outcome.</p>
                )}
                {outcome.pairs.map((pair) => (
                  <article
                    className="coverage-pair"
                    key={pair.task_requirement.id}
                  >
                    <h3>
                      {pair.task_requirement.label || "Assessment requirement"}
                    </h3>
                    <p>{pair.task_requirement.content}</p>
                    <span>
                      {(pair.verdict || "Not evaluated").replaceAll("_", " ")}
                      {pair.link ? ` · ${pair.link.status}` : ""}
                    </span>
                    {pair.rationale && <p>{pair.rationale}</p>}
                    {pair.error && <p className="error">{pair.error}</p>}
                  </article>
                ))}
              </details>
            ))}
          </section>
        ) : (
          !error && (
            <div className="coverage-empty document-empty">
              <h2>
                {documents.length === 0
                  ? "Upload your documents to get started"
                  : paperId &&
                      (overviews.length === 0 || assessments.length === 0)
                    ? "This paper needs more documents"
                    : "Ready to check coverage?"}
              </h2>
              <p>
                {documents.length === 0 ||
                (paperId &&
                  (overviews.length === 0 || assessments.length === 0))
                  ? "Upload a component overview containing learning outcomes and an assessment brief containing tasks."
                  : "Select a paper, learning outcome document and assessment brief in the sidebar, then perform the analysis."}
              </p>
              <Link className="primary" href="/documents">
                Upload documents →
              </Link>
            </div>
          )
        )}
      </main>
    </div>
  );
}
