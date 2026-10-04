"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useWorkspace } from "@/store/workspace";
export function Header() {
  const session = useWorkspace((s) => s.session);
  const logout = useWorkspace((s) => s.logout);
  const pathname = usePathname();
  const router = useRouter();
  return (
    <header className="header">
      <Link href="/" className="brand">
        <span className="brand-mark">K</span> Knowledge
        <span className="brand-light">workspace</span>
      </Link>
      <nav aria-label="Main navigation">
        <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>
          Conversations
        </Link>
        <Link
          href="/dashboard"
          aria-current={pathname === "/dashboard" ? "page" : undefined}
        >
          Paper library
        </Link>
        {session ? (
          <details className="user-menu">
            <summary>
              <span className="avatar">{session.email[0].toUpperCase()}</span>
              <span className="user-email">{session.email}</span>
              <span>⌄</span>
            </summary>
            <div className="dropdown">
              <button
                onClick={() => {
                  logout();
                  router.replace("/auth");
                }}
              >
                Log out
              </button>
            </div>
          </details>
        ) : (
          <Link className="sign-in" href="/auth">
            Sign in →
          </Link>
        )}
      </nav>
    </header>
  );
}
