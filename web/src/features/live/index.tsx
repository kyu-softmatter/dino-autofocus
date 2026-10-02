import { LiveView } from "./LiveView";

/**
 * The live area (owned by the shell, T-010). Route: `#/live` (no `rest` forms yet).
 */
export default function LiveScreen() {
  return (
    <section aria-label="Live view">
      <h2>Live view</h2>
      <LiveView />
    </section>
  );
}
