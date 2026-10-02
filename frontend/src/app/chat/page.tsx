"use client";

import {
  ArrowUp,
  BookOpen,
  ChevronDown,
  CircleUserRound,
  Files,
  LogOut,
  Menu,
  MessageCircle,
  MessageSquarePlus,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, KeyboardEvent, useEffect, useState } from "react";

type Message = { id: number; role: "user" | "assistant"; content: string };

const initialMessages: Message[] = [
  {
    id: 1,
    role: "assistant",
    content:
      "Welcome to your workspace. Ask me about your source documents, or start by uploading a paper from the document library.",
  },
];

export default function ChatPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState(initialMessages);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    setEmail(window.localStorage.getItem("knowledge_email") ?? "");
  }, []);

  function signOut() {
    window.localStorage.removeItem("knowledge_token");
    window.localStorage.removeItem("knowledge_email");
    window.location.href = "/";
  }

  function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const content = message.trim();
    if (!content) return;
    setMessages((current) => [
      ...current,
      { id: Date.now(), role: "user", content },
      {
        id: Date.now() + 1,
        role: "assistant",
        content:
          "I have your question. Connect the chat service to begin answering from your uploaded sources.",
      },
    ]);
    setMessage("");
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  if (!email) {
    return (
      <main className="chat-auth-gate">
        <Sparkles size={22} />
        <h1>Sign in to open your conversations.</h1>
        <Link className="primary-button" href="/">
          Go to sign in
        </Link>
      </main>
    );
  }

  return (
    <main className="app-shell chat-shell">
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
      <section className="main-area chat-main">
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
            <strong>New chat</strong>
          </div>
          <div className="account-menu">
            <div className="account-avatar">
              <CircleUserRound size={18} />
            </div>
            <span className="account-email">{email}</span>
            <ChevronDown size={15} />
            <button className="logout-button" onClick={signOut} title="Log out">
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <div className="chat-content">
          <div className="chat-heading">
            <p className="eyebrow">Source-grounded assistant</p>
            <h1>What are you working on?</h1>
            <p>
              Ask a question about your documents or start a new line of
              thinking.
            </p>
          </div>
          <div className="message-container" aria-live="polite">
            {messages.map((item) => (
              <div className={`message-row ${item.role}`} key={item.id}>
                <div className="message-avatar">
                  {item.role === "assistant" ? (
                    <Sparkles size={16} />
                  ) : (
                    <CircleUserRound size={16} />
                  )}
                </div>
                <div className="message-bubble">
                  <span className="message-label">
                    {item.role === "assistant" ? "Workspace assistant" : "You"}
                  </span>
                  <p>{item.content}</p>
                </div>
              </div>
            ))}
          </div>
          <form className="composer-wrap" onSubmit={sendMessage}>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Message your workspace..."
              rows={1}
              aria-label="Message your workspace"
            />
            <button
              className="send-button"
              type="submit"
              disabled={!message.trim()}
              aria-label="Send message"
            >
              <ArrowUp size={18} />
            </button>
            <p className="composer-note">
              Press Enter to send · Shift + Enter for a new line
            </p>
          </form>
        </div>
      </section>
    </main>
  );
}
