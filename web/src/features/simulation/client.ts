import { createContext, useContext } from "react";

import type { FrameJson } from "./frame";
import type { RunSeriesJson, SimRunInfoJson, ZipEntryJson } from "./types";

/** What the simulation screen reads. Every call is a GET, so remote viewing works too. */
export interface SimulationClient {
  /** "mock" for the in-browser fake, "server" for the API */
  readonly source: "mock" | "server";
  listRuns(): Promise<SimRunInfoJson[]>;
  getRun(runId: string): Promise<SimRunInfoJson>;
  getSeries(runId: string): Promise<RunSeriesJson>;
  getFrame(runId: string, index: number, fields?: string[]): Promise<FrameJson>;
  zipEntries(runId: string): Promise<ZipEntryJson[]>;
  /** where the run's zip downloads from; null when this client cannot serve one */
  zipUrl(runId: string, includeOptional: boolean): string | null;
}

export class ClientError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ClientError";
  }
}

/**
 * The server's routes under /api/simulation (server/api/simulation.py, T-012 stage 2 after T-009).
 * Paths are this screen's proposal until that router is merged.
 */
export function httpClient(base = "/api/simulation", fetchFn: typeof fetch = fetch): SimulationClient {
  const run = (id: string) => `${base}/runs/${encodeURIComponent(id)}`;
  async function get<T>(url: string): Promise<T> {
    const r = await fetchFn(url, { headers: { Accept: "application/json" } });
    if (!r.ok) {
      let detail = r.statusText;
      try {
        const body = (await r.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // not JSON: keep the status text
      }
      throw new ClientError(`${url}: ${r.status} ${detail}`, r.status);
    }
    return (await r.json()) as T;
  }
  return {
    source: "server",
    listRuns: () => get(`${base}/runs`),
    getRun: (id) => get(run(id)),
    getSeries: (id) => get(`${run(id)}/series`),
    getFrame: (id, index, fields = []) => {
      const q = fields.length ? `?fields=${fields.map(encodeURIComponent).join(",")}` : "";
      return get(`${run(id)}/frames/${index}${q}`);
    },
    zipEntries: (id) => get(`${run(id)}/zip/entries`),
    zipUrl: (id, includeOptional) => `${run(id)}/zip${includeOptional ? "?trajectory=1" : ""}`,
  };
}

export const SimulationClientContext = createContext<SimulationClient | null>(null);

export function useSimulationClient(fallback: () => SimulationClient): SimulationClient {
  return useContext(SimulationClientContext) ?? fallback();
}
