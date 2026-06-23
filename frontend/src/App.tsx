import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandCenter } from "@/screens/CommandCenter";

export default function App() {
  return (
    <ErrorBoundary label="The command center hit an error">
      <CommandCenter />
    </ErrorBoundary>
  );
}
