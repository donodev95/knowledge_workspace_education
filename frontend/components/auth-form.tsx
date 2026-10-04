"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useWorkspace } from "@/store/workspace";
export function Login() {
  return <AuthForm mode="login" />;
}
export function Register() {
  return <AuthForm mode="register" />;
}
export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const register = mode === "register";
  const router = useRouter();
  const signIn = useWorkspace((s) => s.signIn);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email")).trim().toLowerCase();
    const password = String(form.get("password"));
    setBusy(true);
    setError("");
    try {
      if (register)
        await api("/auth/register", null, {
          method: "POST",
          body: JSON.stringify({
            username: String(form.get("username")).trim(),
            email,
            password,
          }),
        });
      const result = await api<{ access_token: string; expires_in: number }>(
        "/auth/login",
        null,
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      signIn(email, result.access_token, result.expires_in);
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-intro">
        <span className="eyebrow">YOUR KNOWLEDGE, CONNECTED</span>
        <h1>
          A little clarity.
          <br />A lot of possibility.
        </h1>
        <p>
          Bring your papers together. Ask better questions. Find answers
          grounded in your documents.
        </p>
        <div className="intro-note">
          <span>✦</span> A workspace for your next discovery.
        </div>
      </section>
      <section className="auth-card">
        <span className="eyebrow">LET’S GET STARTED</span>
        <h2>{register ? "Create your account" : "Welcome back"}</h2>
        <p>
          {register
            ? "Make room for your ideas."
            : "Pick up where you left off."}
        </p>
        <form onSubmit={submit}>
          {register && (
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                placeholder="Your username"
                required
                minLength={3}
                maxLength={50}
                pattern="[A-Za-z0-9_.-]+"
              />
            </label>
          )}
          <label>
            Email address
            <input
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              required
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="At least 8 characters"
              required
              minLength={8}
              maxLength={128}
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy
              ? "Please wait…"
              : register
                ? "Create account →"
                : "Sign in →"}
          </button>
        </form>
        <p className="auth-switch">
          {register ? "Already have an account?" : "New to Knowledge?"}{" "}
          <Link href={register ? "/login" : "/register"}>
            {register ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </section>
    </main>
  );
}
