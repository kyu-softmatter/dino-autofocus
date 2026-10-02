/**
 * Temporary until gen:api covers the hardware router (T-009): hand-written types for
 * `/api/hardware/*` (docs/screens/hardware.md 1) and `/api/permissions` (T-009b), and the
 * reads that use them. Commands, events and `/api/state` already go through the shell's
 * client (`src/app/client.tsx`). When `src/api/schema.ts` has these paths, swap the types
 * below for imports from it; nothing else changes.
 */

import type { Client } from "../../app/client";

export interface DeviceRow {
  label: string;
  role?: string;
  type?: string;
  library?: string;
  present: boolean;
  /** a read of its state succeeded and was checked; null = not reported */
  read_back: boolean | null;
  /** a write was read back correctly; null = not tested yet (ops-spec 5) */
  write_verified: boolean | null;
  note?: string;
}

export interface ObjectiveRow {
  label: string;
  state?: number;
  magnification?: number;
  na?: number;
  immersion?: string;
  working_distance_um?: number | null;
  pixel_um?: number;
}

export interface ConfirmedItem {
  value: string;
  by?: string;
  at?: string;
}

export interface HardwareProfile {
  detected_at: string;
  backend: string;
  host?: string;
  config?: { path?: string; sha256?: string; changed_during_load?: boolean; startup_preset_applied?: boolean };
  /** sha256 of the previous profile; null = no previous profile */
  previous_sha256?: string | null;
  /** top-level keys that differ from the previous profile */
  changed?: string[];
  devices: DeviceRow[];
  objectives: ObjectiveRow[];
  camera?: { name?: string; sensor?: [number, number]; bit_depth?: number; ceiling_adu?: number; pixel_type?: string };
  piezo?: { port?: string; connected?: boolean; z_um?: number | null; error?: string | null };
  human_confirmed: Record<string, ConfirmedItem>;
}

export interface HardwareProfileOut {
  profile: HardwareProfile | null;
  path: string | null;
  sha256: string | null;
}

export interface GateRow {
  op: string;
  enabled: boolean;
  reasons: string[];
  requires: { devices: string[]; objectives: string[]; confirmed: string[] };
}

/** `summary` of the last `finished(status)` (ops-spec 2). */
export interface StatusSummary {
  nosepiece_label?: string;
  nosepiece_state?: number;
  z_um?: number | null;
  pfs_enabled?: boolean | string;
  pfs_locked?: boolean | string;
  pfs_in_range?: string;
}

export interface StatusResultOut {
  op_id: string;
  t: number;
  user_id: string | null;
  summary: StatusSummary;
}

/** `GET /api/permissions?ops=...` (T-009b, from T-011 `check()`): why a command would be refused. */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}

export type Permissions = Record<string, Permission>;

/** The commands this screen sends; `lights_off` is a command kind, the rest are `start` ops. */
export const SCREEN_OPS = ["hardware_scan", "hardware_confirm", "status", "light_set", "lights_off"] as const;

/** Shared texts for every screen (screen rules from AF 업무분배보조). */
export const CHECKING_PERMISSIONS = "Checking permissions…";
export const PERMISSION_CHECK_UNAVAILABLE = "Permission check unavailable";
export const READ_ONLY_REMOTE = "Read-only: remote view";

export const PATHS = {
  profile: "/api/hardware/profile",
  gates: "/api/hardware/gates",
  status: "/api/hardware/status",
  permissions: (ops: readonly string[]) => `/api/permissions?ops=${ops.map(encodeURIComponent).join(",")}`,
};

/**
 * When `/api/permissions` cannot be read, every control is off with the shared reason.
 * The exception is `lights_off`: a stop stays available, like the shell's Abort and Lights
 * off. A remote screen still greys it out through the shell's read-only flag (D2).
 */
export function permissionsUnavailable(ops: readonly string[]): Permissions {
  const out: Permissions = {};
  for (const op of ops) {
    out[op] = op === "lights_off"
      ? { allowed: true, reason: null }
      : { allowed: false, reason: PERMISSION_CHECK_UNAVAILABLE };
  }
  return out;
}

export async function readPermissions(client: Client, ops: readonly string[]): Promise<Permissions> {
  try {
    return await client.get<Permissions>(PATHS.permissions(ops));
  } catch {
    return permissionsUnavailable(ops);
  }
}

export const readProfile = (client: Client) => client.get<HardwareProfileOut>(PATHS.profile);
export const readGates = (client: Client) => client.get<GateRow[]>(PATHS.gates);
export const readStatus = (client: Client) => client.get<StatusResultOut | null>(PATHS.status);
