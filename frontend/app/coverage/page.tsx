import { CoverageAnalysis } from "@/components/coverage-analysis";
import { WorkspaceShell } from "@/components/workspace-shell";

export default function Page() {
  return <WorkspaceShell><CoverageAnalysis /></WorkspaceShell>;
}
