import { type ComponentType, lazy, Suspense } from "react";

/**
 * Where the shared prompt box sits on every screen (PLAN X1). The component is
 * T-014's, in `src/app/assistant/index.tsx` (default export, no props; it reads
 * the screen with useCurrentScreenContext). Until that file exists the slot
 * shows a placeholder.
 */
const found = import.meta.glob<{ default: ComponentType }>("./assistant/index.tsx");

export function assistantLoaderFrom(modules: Record<string, () => Promise<{ default: ComponentType }>>) {
  return Object.values(modules)[0];
}

const load = assistantLoaderFrom(found);
const PromptBox = load ? lazy(load) : null;

export function AssistantSlot() {
  return (
    <section className="assistant-slot" aria-label="Prompt">
      {PromptBox ? (
        <Suspense fallback={<p className="muted">Loading prompt box…</p>}>
          <PromptBox />
        </Suspense>
      ) : (
        <p className="muted">Prompt box: not implemented yet</p>
      )}
    </section>
  );
}
