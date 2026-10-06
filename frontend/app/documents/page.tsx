import { Documents } from "@/components/dashboard";
import { WorkspaceShell } from "@/components/workspace-shell";
export default function Page() {
  return (
    <WorkspaceShell>
      <p>Welcome to the Dashboard</p>
      <Documents />
    </WorkspaceShell>
  );
}
