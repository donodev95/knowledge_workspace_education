import { ChatWorkspace } from "@/components/chat-workspace";
import { WorkspaceShell } from "@/components/workspace-shell";
export default function Home() {
  return (
    <WorkspaceShell>
      <ChatWorkspace />
    </WorkspaceShell>
  );
}
