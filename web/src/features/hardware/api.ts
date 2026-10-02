/**
 * Temporary until gen:api covers the hardware router (T-009): hand-written types for
 * `/api/hardware/*` (docs/screens/hardware.md 1) and `/api/permissions` (T-009b), and the
 * reads that use them. Commands, events and `/api/state` already go through the shell's
 * client (`src/app/client.tsx`). When `src/api/schema.ts` has these paths, swap the types
 * below for imports from it; nothing else changes.
 */

import type { Client } from "../../app/client";

// Shapes follow server/api/hardware.py, which reshapes T-028 `engine.gates` (55d88c2).

export interface DeviceRow {
  label: string;
  role?: string | null;
  type?: string | null;
  library?: string | null;
  description?: string | null;
  present: boolean;
  /** a read of its state succeeded and was checked; null = not reported */
  read_back: boolean | null;
  /** a write was read back correctly; null = not tested yet (ops-spec 5) */
  write_verified: boolean | null;
  note?: string | null;
}

export interface ObjectiveRow {
  label: string;
  state?: number | null;
  magnification?: number | null;
  registry_key?: string | null;
  na?: number | null;
  immersion?: string | null;
  working_distance_um?: number | null;
  /** where the working distance came from: the backend or the guards' lens table */
  wd_source?: string | null;
  pixel_um?: number | null;
}

export interface ConfirmedItem {
  value: string;
  by?: string;
  at?: string;
}

export interface HardwareProfile {
  detected_at: string;
  backend_kind: string;
  host?: string | null;
  bench?: boolean | null;
  /** nosepiece label at detection time */
  objective?: string | null;
  config?: { path?: string; sha256?: string; changed_during_load?: boolean; startup_preset_applied?: boolean } | null;
  devices: DeviceRow[];
  objectives: ObjectiveRow[];
  camera?: { name?: string | null; sensor?: [number, number] | null; bit_depth?: number | null; ceiling_adu?: number | null; pixel_type?: string | null } | null;
  piezo?: { port?: string | null; connected?: boolean | null; z_um?: number | null; error?: string | null } | null;
  human_confirmed: Record<string, ConfirmedItem>;
  notes?: Record<string, string>;
  /** section -> why its read failed */
  errors?: Record<string, string>;
}

/** The latest profile's diff against the one before (T-028 `ProfileStore.previous`). */
export interface PreviousProfile {
  sha256?: string | null;
  detected_at?: string | null;
  changed: { key: string; before?: unknown; after?: unknown }[];
}

export interface HardwareProfileOut {
  profile: HardwareProfile | null;
  path: string | null;
  sha256: string | null;
  /** null: no previous profile */
  previous?: PreviousProfile | null;
  /** the engine could not read its hardware state */
  error?: string | null;
}

export interface GateRow {
  /** the gate key: the op, or `op:value` for a per-argument row, e.g. `light_set:aura` */
  op: string;
  enabled: boolean;
  reasons: string[];
  requires: {
    devices: string[];
    objectives: string[];
    confirmed: string[];
    /** profile checks, e.g. camera_bit_depth */
    checks: string[];
    /** the argument value this row is for, e.g. {mode: "aura"} */
    arg: Record<string, string> | null;
  };
}

/** The gate key for `light_set` in one mode (T-028: one row per mode). */
export const lightGateKey = (mode: "brightfield" | "aura" | "off") => `light_set:${mode}`;

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
