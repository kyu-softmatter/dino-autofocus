import type { Transport } from "../app/client";

/** A WebSocket stand-in the test drives by hand. */
export class FakeSocket {
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  closed = false;

  constructor(public path: string) {}

  open(): void {
    this.onopen?.(new Event("open"));
  }

  send(data: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: typeof data === "string" ? data : JSON.stringify(data) }));
  }

  event(kind: string, data: Record<string, unknown> = {}, op_id = ""): void {
    this.send({ type: "event", event: { kind, op_id, data, t: 1 } });
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.(new CloseEvent("close"));
  }
}

export type Route = (init?: RequestInit) => { status: number; body?: unknown };

/** A transport whose fetch answers from a table of paths and whose sockets are FakeSockets. */
export function fakeTransport(routes: Record<string, Route>) {
  const sockets: FakeSocket[] = [];
  const calls: { path: string; init?: RequestInit }[] = [];
  const transport: Transport = {
    fetch: async (path, init) => {
      calls.push({ path, init });
      const route = routes[path];
      const { status, body } = route ? route(init) : { status: 404, body: { detail: "Not Found" } };
      return new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    },
    openSocket: (path) => {
      const s = new FakeSocket(path);
      sockets.push(s);
      return s as unknown as WebSocket;
    },
  };
  return { transport, sockets, calls };
}
