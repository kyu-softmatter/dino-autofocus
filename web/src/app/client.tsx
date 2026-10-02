import { createContext, type ReactNode, useContext, useEffect, useState, useSyncExternalStore } from "react";

import type { components } from "../api/schema";

export type CommandIn = components["schemas"]["CommandIn"];
/** What a screen sends: `kind` and whatever differs from the server's defaults (op, op_id, args, origin). */
export type CommandInput = Pick<CommandIn, "kind"> & Partial<Omit<CommandIn, "kind">>;
export type EventOut = components["schemas"]["EventOut"];
export type EventKind = EventOut["kind"];
type WsEvent = components["schemas"]["WsEvent"];

/**
 * Everything the shell and the screens need from the server, in one injectable
 * object: tests pass fakes, the app uses the browser's fetch and WebSocket.
 */
export interface Transport {
  fetch: (path: string, init?: RequestInit) => Promise<Response>;
  openSocket: (path: string) => WebSocket;
}

export const browserTransport: Transport = {
  fetch: (path, init) => window.fetch(path, init),
  openSocket: (path) => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return new WebSocket(`${proto}//${window.location.host}${path}`);
  },
};

// -- read-only (remote view) -----------------------------------------------------------

const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

export function isLoopbackHost(hostname: string): boolean {
  return LOOPBACK.has(hostname) || hostname.endsWith(".localhost");
}

export interface ReadOnlyState {
  readOnly: boolean;
  why: string | null;
}

/**
 * Whether this browser may send commands. Starts from the page's host (a remote
 * viewer reaches the server by a non-loopback name) and turns on for good when
 * the server answers a command with 403. The server decides; this only greys
 * out buttons so people are not surprised.
 */
export class ReadOnlyStore {
  private state: ReadOnlyState;
  private listeners = new Set<() => void>();

  constructor(hostname: string) {
    this.state = isLoopbackHost(hostname)
      ? { readOnly: false, why: null }
      : { readOnly: true, why: "remote view" };
  }

  get = (): ReadOnlyState => this.state;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  refuse(why: string): void {
    if (this.state.readOnly && this.state.why === why) return;
    this.state = { readOnly: true, why };
    this.listeners.forEach((fn) => fn());
  }
}

// -- events -----------------------------------------------------------------------------

export type EventHandler = (ev: EventOut) => void;

/**
 * One `/ws/events` connection shared by the whole app. Reconnects with backoff;
 * `onStatus` says whether it is open. After a reconnect, screens should re-read
 * state (events in between are lost), so listeners get `connected` again.
 */
export class EventStream {
  private socket: WebSocket | null = null;
  private handlers = new Set<EventHandler>();
  private statusListeners = new Set<(open: boolean) => void>();
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  open = false;

  constructor(
    private transport: Transport,
    private path = "/ws/events",
    private backoffMs = (n: number) => Math.min(500 * 2 ** n, 10_000),
  ) {}

  start(): void {
    if (this.socket || this.closed) return;
    const ws = this.transport.openSocket(this.path);
    this.socket = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setOpen(true);
    };
    ws.onmessage = (msg) => {
      if (typeof msg.data !== "string") return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(msg.data);
      } catch {
        return;
      }
      const m = parsed as Partial<WsEvent>;
      if (m.type === "event" && m.event) this.handlers.forEach((h) => h(m.event as EventOut));
    };
    ws.onclose = () => {
      this.socket = null;
      this.setOpen(false);
      if (this.closed) return;
      this.timer = setTimeout(() => this.start(), this.backoffMs(this.retry++));
    };
  }

  stop(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.socket?.close();
    this.socket = null;
  }

  on(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onStatus(fn: (open: boolean) => void): () => void {
    this.statusListeners.add(fn);
    return () => this.statusListeners.delete(fn);
  }

  private setOpen(open: boolean): void {
    this.open = open;
    this.statusListeners.forEach((fn) => fn(open));
  }
}

// -- the client -------------------------------------------------------------------------

export class CommandRefused extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

export class Client {
  readonly readOnly: ReadOnlyStore;
  readonly events: EventStream;

  constructor(
    readonly transport: Transport,
    hostname: string,
  ) {
    this.readOnly = new ReadOnlyStore(hostname);
    this.events = new EventStream(transport);
  }

  private authListeners = new Set<(status: number) => void>();

  /**
   * Called on any 401 (logged out) or 423 (locked) answer. The login gate uses it
   * to re-read /me and show the login or lock screen.
   */
  onAuthFailure(fn: (status: number) => void): () => void {
    this.authListeners.add(fn);
    return () => this.authListeners.delete(fn);
  }

  private check(r: Response): void {
    if (r.status === 401 || r.status === 423) this.authListeners.forEach((fn) => fn(r.status));
  }

  async get<T = unknown>(path: string): Promise<T> {
    const r = await this.transport.fetch(path, { headers: { Accept: "application/json" } });
    this.check(r);
    if (!r.ok) throw new CommandRefused(r.status, await detailOf(r));
    return (await r.json()) as T;
  }

  /**
   * POST JSON to an area's own route (console submit, map writes, sessions, auth...).
   * The same rules as `command`: a 403 switches the app to read-only, a 401 / 423
   * re-reads the login. Returns the JSON reply, or null for an empty one (204).
   * Engine commands go through `command`, not here.
   */
  async post<T = unknown>(path: string, body?: unknown): Promise<T | null> {
    const r = await this.transport.fetch(path, {
      method: "POST",
      headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    this.check(r);
    if (r.status === 403) {
      const why = await detailOf(r);
      this.readOnly.refuse(why);
      throw new CommandRefused(403, why);
    }
    if (!r.ok) throw new CommandRefused(r.status, await detailOf(r));
    if (r.status === 204) return null;
    const text = await r.text();
    return text === "" ? null : (JSON.parse(text) as T);
  }

  /** POST /api/commands (engine commands). A 403 (remote view, D13) switches the app to read-only. */
  async command(cmd: CommandInput): Promise<string> {
    const reply = await this.post<components["schemas"]["CommandAccepted"]>("/api/commands", cmd);
    if (!reply) throw new CommandRefused(502, "the server accepted the command but gave no op_id");
    return reply.op_id;
  }
}

async function detailOf(r: Response): Promise<string> {
  try {
    const body = (await r.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`;
  } catch {
    return `HTTP ${r.status}`;
  }
}

const ClientCtx = createContext<Client | null>(null);

export function ClientProvider({ client, children }: { client: Client; children: ReactNode }) {
  useEffect(() => {
    client.events.start();
  }, [client]);
  return <ClientCtx.Provider value={client}>{children}</ClientCtx.Provider>;
}

export function useClient(): Client {
  const c = useContext(ClientCtx);
  if (c === null) throw new Error("ClientProvider is missing (main.tsx provides it)");
  return c;
}

/** For screens: grey out command buttons when this is true. The server refuses anyway. */
export function useReadOnly(): ReadOnlyState {
  const { readOnly } = useClient();
  return useSyncExternalStore(readOnly.subscribe, readOnly.get);
}

/** For screens: call `handler` for engine events (optionally only some kinds). */
export function useEngineEvents(handler: EventHandler, kinds?: readonly EventKind[]): void {
  const { events } = useClient();
  const key = kinds?.join(",") ?? "";
  useEffect(() => {
    const only = key ? new Set(key.split(",")) : null;
    return events.on((ev) => {
      if (!only || only.has(ev.kind)) handler(ev);
    });
  }, [events, handler, key]);
}

/** Whether the event socket is open. */
export function useEventsConnected(): boolean {
  const { events } = useClient();
  const [open, setOpen] = useState(events.open);
  useEffect(() => events.onStatus(setOpen), [events]);
  return open;
}
