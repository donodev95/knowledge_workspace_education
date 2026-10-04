import { Dashboard } from "@/components/dashboard";
import { WorkspaceShell } from "@/components/workspace-shell";
export default function Page() {
  return (
    <WorkspaceShell>
      <Dashboard />
    </WorkspaceShell>
  );
}
