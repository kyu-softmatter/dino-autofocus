import { useState } from "react";

import { type Client, ClientProvider, useReadOnly } from "./client";
import { Shell } from "./Shell";
import { useAssistantStatus, useEngineStatus } from "./status";
import { ShutdownNoticeView, StatusBarView } from "./StatusBar";

function Connected() {
  const status = useEngineStatus();
  const assistant = useAssistantStatus();
  const readOnly = useReadOnly();
  const [dismissed, setDismissed] = useState(false);
  return (
    <Shell
      statusBar={<StatusBarView status={status} assistant={assistant} readOnly={readOnly} />}
      notice={
        dismissed ? null : (
          <ShutdownNoticeView last={status.lastShutdown} onDismiss={() => setDismissed(true)} />
        )
      }
    />
  );
}

/** The whole app: the server client, then the shell with the live status bar. */
export function App({ client }: { client: Client }) {
  return (
    <ClientProvider client={client}>
      <Connected />
    </ClientProvider>
  );
}
