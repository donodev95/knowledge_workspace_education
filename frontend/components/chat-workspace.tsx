"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Conversation, Message, useWorkspace } from "@/store/workspace";

export function ChatWorkspace() {
  const {
    session,
    conversations,
    activeId,
    messages,
    setConversations,
    selectConversation,
    setMessages,
  } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const current = activeId ? (messages[activeId] ?? []) : [];
  useEffect(() => {
    let cancelled = false;
    api<Conversation[]>("/threads", session!.token)
      .then((items) => {
        if (!cancelled) setConversations(items);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [session, setConversations]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeId]);
  async function openConversation(id: string) {
    selectConversation(id);
    setError("");
    setLoading(true);
    try {
      const history = await api<Message[]>(
        `/chat/${id}/history`,
        session!.token,
      );
      setMessages(id, history);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load conversation");
    } finally {
      setLoading(false);
    }
  }
  async function send(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || sending || loading) return;
    setSending(true);
    setError("");
    try {
      let id = activeId;
      if (!id) {
        const thread = await api<Conversation>("/threads", session!.token, {
          method: "POST",
          body: JSON.stringify({ title: text.slice(0, 100) }),
        });
        id = thread.id;
        setConversations([thread, ...useWorkspace.getState().conversations]);
        selectConversation(id);
      }
      // Keep the draft until the request succeeds so a failed send is easy to retry.
      const result = await api<{
        message_id: string;
        answer: string;
        sources: Message["sources"];
      }>(`/chat/${id}`, session!.token, {
        method: "POST",
        body: JSON.stringify({ question: text }),
      });
      const history = useWorkspace.getState().messages[id] ?? [];
      setMessages(id, [
        ...history,
        { id: crypto.randomUUID(), role: "user", content: text },
        {
          id: result.message_id,
          role: "assistant",
          content: result.answer,
          sources: result.sources,
        },
      ]);
      setQuestion("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to send message");
    } finally {
      setSending(false);
    }
  }
  return (
    <div className="workspace">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        disabled={sending || loading}
        onCreate={() => {
          selectConversation(null);
          setQuestion("");
          setError("");
        }}
        onSelect={openConversation}
      />
      <main className="chat-main">
        <div className="section-bar">
          <span>
            {conversations.find((c) => c.id === activeId)?.title ??
              "New conversation"}
          </span>
          <span className="status-dot">Source-grounded answers</span>
        </div>
        <div
          className="messages"
          role="log"
          aria-label="Conversation messages"
          aria-live="polite"
        >
          {loading ? (
            <p className="loading">Loading conversation…</p>
          ) : current.length === 0 ? (
            <EmptyConversation onPrompt={setQuestion} />
          ) : (
            <div className="message-list">
              {current.map((message) => (
                <article key={message.id} className={`message ${message.role}`}>
                  <span className="message-label">
                    {message.role === "user" ? "You" : "Knowledge"}
                  </span>
                  <p>{message.content}</p>
                  {!!message.sources?.length && (
                    <div className="citations">
                      {message.sources.map((source, i) => (
                        <span key={i}>
                          {source.document_name ?? "Source"}
                          {source.page_number
                            ? ` · p. ${source.page_number}`
                            : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          {sending && (
            <p className="thinking" role="status">
              Looking through your documents…
            </p>
          )}
          <div ref={bottom} />
        </div>
        <div className="composer-area">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <form className="composer" onSubmit={send}>
            <label className="sr-only" htmlFor="question">
              Your message
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about your papers…"
              maxLength={4000}
              rows={2}
              disabled={sending || loading}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-footer">
              <span>↵ to send · Shift + Enter for a new line</span>
              <button
                className="primary"
                disabled={!question.trim() || sending || loading}
              >
                {sending ? "Sending…" : "Send ↑"}
              </button>
            </div>
          </form>
          <p className="composer-note">
            Answers are based on your uploaded documents. Always review the
            sources.
          </p>
        </div>
      </main>
    </div>
  );
}
export function Sidebar({
  conversations,
  activeId,
  disabled,
  onCreate,
  onSelect,
}: {
  conversations: Conversation[];
  activeId: string | null;
  disabled: boolean;
  onCreate: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <button className="new-chat" onClick={onCreate} disabled={disabled}>
        <span>＋</span> Create chat
      </button>
      <div className="sidebar-label">
        YOUR CONVERSATIONS <span>{conversations.length}</span>
      </div>
      <div className="conversation-list">
        {conversations.length ? (
          conversations.map((c) => (
            <button
              key={c.id}
              disabled={disabled}
              className={
                activeId === c.id ? "conversation active" : "conversation"
              }
              onClick={() => onSelect(c.id)}
            >
              <span>◷</span>
              <span>{c.title}</span>
            </button>
          ))
        ) : (
          <p className="sidebar-empty">
            Your conversations will appear here. Start with a question.
          </p>
        )}
      </div>
      <Link className="sidebar-library" href="/dashboard">
        <span>▤</span> Manage your papers <span>↗</span>
      </Link>
      <div className="sidebar-note">
        Good questions start
        <br />
        with good sources.
      </div>
    </aside>
  );
}
export function EmptyConversation({
  onPrompt,
}: {
  onPrompt: (text: string) => void;
}) {
  return (
    <section className="empty-conversation">
      <div className="spark">✦</div>
      <span className="eyebrow">A SPACE TO THINK</span>
      <h1>
        What would you like
        <br />
        to understand?
      </h1>
      <p>
        Explore your papers, connect ideas, and find
        <br className="desktop-break" /> answers with the sources to back them
        up.
      </p>
      <div className="prompt-grid">
        {[
          "Summarize the key ideas in my papers",
          "Help me understand an assessment",
          "Compare concepts across my documents",
        ].map((text, i) => (
          <button key={text} onClick={() => onPrompt(text)}>
            <span className="prompt-icon">{["▤", "◇", "⇄"][i]}</span>
            {text}
            <span>↗</span>
          </button>
        ))}
      </div>
      <Link className="text-link" href="/dashboard">
        Add your first paper to get started →
      </Link>
    </section>
  );
}
