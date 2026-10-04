"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useWorkspace } from "@/store/workspace";
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const session = useWorkspace((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/auth");
  }, [session, router]);
  return session ? (
    <>{children}</>
  ) : (
    <main className="loading">Opening sign in…</main>
  );
}
