// Temporary until gen:api, T-009: the auth API types and clients are written by hand from
// docs/screens/login.md section 1. Once server/api/auth.py is in and `npm run gen:api` has run,
// the types come from src/api/ and this file keeps only the clients.

export type Role = "admin" | "operator" | "viewer";
export type SetupState = "needs_admin_email" | "needs_admin" | "ready";
export type LoginFailure = "bad_credentials" | "pending_approval" | "disabled";

export interface Me {
  user_id: string;
  name: string;
  role: Role;
  locked: boolean;
  has_control: boolean;
  /** the browser runs on the microscope PC; write controls work only then (D16) */
  local: boolean;
  expires_at: number;
}

export interface Account {
  email: string;
  name: string;
  role: Role;
  status: "pending" | "active" | "disabled";
  created_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

/** A failed call. `status` is the HTTP status; `outcome` is set on a failed login. */
export class AuthError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly outcome?: LoginFailure,
  ) {
    super(message);
  }
}

export interface AuthApi {
  setup(): Promise<SetupState>;
  createAdmin(body: { name: string; password: string; email?: string }): Promise<Me>;
  signup(body: { name: string; email: string; password: string }): Promise<void>;
  login(body: { email: string; password: string }): Promise<Me>;
  logout(): Promise<void>;
  lock(): Promise<void>;
  unlock(body: { password: string }): Promise<Me>;
  /** null when not logged in (401) */
  me(): Promise<Me | null>;
  pending(): Promise<Account[]>;
  approve(email: string, role: Role): Promise<Account>;
}

// -- the real client: same origin, the session cookie rides along -----------------------------

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/auth${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string; outcome?: LoginFailure };
    throw new AuthError(res.status, err.detail ?? res.statusText, err.outcome);
  }
  return res.status === 204 || res.status === 201 ? (undefined as T) : ((await res.json()) as T);
}

export const httpAuthApi: AuthApi = {
  setup: async () => (await call<{ state: SetupState }>("GET", "/setup")).state,
  createAdmin: (body) => call("POST", "/setup/admin", body),
  signup: (body) => call("POST", "/signup", body),
  login: (body) => call("POST", "/login", body),
  logout: () => call("POST", "/logout"),
  lock: () => call("POST", "/lock"),
  unlock: (body) => call("POST", "/unlock", body),
  me: async () => {
    try {
      return await call<Me>("GET", "/me");
    } catch (e) {
      if (e instanceof AuthError && e.status === 401) return null;
      throw e;
    }
  },
  pending: () => call("GET", "/accounts?status=pending"),
  approve: (email, role) => call("POST", `/accounts/${encodeURIComponent(email)}/approve`, { role }),
};

// -- the fake client: in memory, for tests and for building the screen before the router ------

interface FakeUser {
  name: string;
  email: string;
  password: string;
  role: Role;
  status: Account["status"];
  created_at: string;
}

export interface FakeAuthApi extends AuthApi {
  /** test hook: lock the current session as the idle timer would */
  lockNow(): void;
  readonly users: FakeUser[];
}

/** Users are example.test addresses only. `local` is what `me()` reports for this browser. */
export function createFakeAuthApi(
  opts: { users?: Omit<FakeUser, "created_at">[]; setup?: SetupState; local?: boolean } = {},
): FakeAuthApi {
  const users: FakeUser[] = (opts.users ?? []).map((u) => ({ ...u, created_at: "2026-10-01T09:00:00+00:00" }));
  let setup: SetupState = opts.setup ?? "ready";
  let current: { email: string; locked: boolean } | null = null;
  const local = opts.local ?? true;
  const find = (email: string) => users.find((u) => u.email === email.trim().toLowerCase());
  const meOf = (u: FakeUser, locked: boolean): Me => ({
    user_id: u.email,
    name: u.name,
    role: u.role,
    locked,
    has_control: false,
    local,
    expires_at: Date.now() / 1000 + 12 * 3600,
  });
  const account = (u: FakeUser): Account => ({
    email: u.email,
    name: u.name,
    role: u.role,
    status: u.status,
    created_at: u.created_at,
    approved_by: null,
    approved_at: null,
  });
  const admin = () => {
    const u = current && find(current.email);
    if (!u || u.role !== "admin" || !local) throw new AuthError(403, "only an admin on the microscope PC");
    return u;
  };

  return {
    users,
    lockNow() {
      if (current) current.locked = true;
    },
    async setup() {
      return setup;
    },
    async createAdmin({ name, password, email }) {
      if (setup === "ready") throw new AuthError(409, "an admin account already exists");
      if (!local) throw new AuthError(403, "set up on the microscope PC");
      const u: FakeUser = {
        name,
        email: (email ?? "admin@example.test").toLowerCase(),
        password,
        role: "admin",
        status: "active",
        created_at: new Date().toISOString(),
      };
      users.push(u);
      setup = "ready";
      current = { email: u.email, locked: false };
      return meOf(u, false);
    },
    async signup({ name, email, password }) {
      if (find(email)) throw new AuthError(409, `an account already exists for ${email.toLowerCase()}`);
      users.push({ name, email: email.trim().toLowerCase(), password, role: "viewer", status: "pending", created_at: new Date().toISOString() });
    },
    async login({ email, password }) {
      const u = find(email);
      if (!u || u.password !== password) throw new AuthError(401, "Wrong email or password.", "bad_credentials");
      if (u.status === "pending")
        throw new AuthError(401, "Your account is waiting for an administrator's approval.", "pending_approval");
      if (u.status === "disabled") throw new AuthError(401, "This account is disabled.", "disabled");
      current = { email: u.email, locked: false };
      return meOf(u, false);
    },
    async logout() {
      current = null;
    },
    async lock() {
      if (current) current.locked = true;
    },
    async unlock({ password }) {
      const u = current && find(current.email);
      if (!u || !current) throw new AuthError(401, "not logged in");
      if (u.password !== password) throw new AuthError(401, "Wrong password.");
      current.locked = false;
      return meOf(u, false);
    },
    async me() {
      const u = current && find(current.email);
      return u && current ? meOf(u, current.locked) : null;
    },
    async pending() {
      admin();
      return users.filter((u) => u.status === "pending").map(account);
    },
    async approve(email, role) {
      admin();
      const u = find(email);
      if (!u || u.status !== "pending") throw new AuthError(409, `${email} is not waiting for approval`);
      u.status = "active";
      u.role = role;
      return account(u);
    },
  };
}
