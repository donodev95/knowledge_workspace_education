"use client";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/store/workspace";
import { Header } from "./header";
export function Providers({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void Promise.resolve(useWorkspace.persist.rehydrate()).then(() => {
      const s = useWorkspace.getState();
      if (s.session && s.session.expiresAt <= Date.now()) s.logout();
      setReady(true);
    });
  }, []);
  return (
    <>
      <Header />
      {ready ? (
        children
      ) : (
        <main className="loading" role="status">
          Loading workspace…
        </main>
      )}
    </>
  );
}
