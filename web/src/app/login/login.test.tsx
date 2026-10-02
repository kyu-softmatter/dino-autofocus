import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { createFakeAuthApi, type Me } from "./api";
import { ApprovalList } from "./ApprovalList";
import { LoginGate, useAuth } from "./LoginGate";

// fake users: example.test addresses only, test passwords only
const USERS = [
  { name: "Ada Admin", email: "admin@example.test", password: "admin-pass-1", role: "admin" as const, status: "active" as const },
  { name: "Otto Operator", email: "otto@example.test", password: "otto-pass-1", role: "operator" as const, status: "active" as const },
  { name: "Pat Pending", email: "pat@example.test", password: "pat-pass-12", role: "viewer" as const, status: "pending" as const },
  { name: "Dee Disabled", email: "dee@example.test", password: "dee-pass-12", role: "viewer" as const, status: "disabled" as const },
];

function App() {
  const auth = useAuth();
  return (
    <div>
      <p>the app for {auth?.me.name}</p>
      <button onClick={() => void auth?.lock()}>Lock</button>
      <button onClick={() => void auth?.logout()}>Log out</button>
    </div>
  );
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function logIn(email: string, password: string) {
  fill("Email", email);
  fill("Password", password);
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
}

function gate(api = createFakeAuthApi({ users: USERS }), abort?: ReactNode) {
  render(
    <LoginGate api={api} abort={abort} pollMs={0}>
      <App />
    </LoginGate>,
  );
  return api;
}

describe("LoginGate", () => {
  it("shows the login form, not the app, until someone logs in", async () => {
    gate();
    await screen.findByRole("form", { name: "Log in" });
    expect(screen.queryByText(/the app for/)).toBeNull();
    await logIn("OTTO@Example.test", "otto-pass-1"); // email without case
    expect(await screen.findByText("the app for Otto Operator")).toBeTruthy();
  });

  it("says why a login failed", async () => {
    gate();
    await screen.findByRole("form", { name: "Log in" });
    await logIn("otto@example.test", "wrong-pass");
    expect((await screen.findByRole("alert")).textContent).toContain("Wrong email or password");
  });

  it("tells a pending account it waits for approval", async () => {
    gate();
    await screen.findByRole("form", { name: "Log in" });
    await logIn("pat@example.test", "pat-pass-12");
    expect((await screen.findByRole("status")).textContent).toContain("waiting for an administrator's approval");
    expect(screen.queryByText(/the app for/)).toBeNull();
  });

  it("tells a disabled account so", async () => {
    gate();
    await screen.findByRole("form", { name: "Log in" });
    await logIn("dee@example.test", "dee-pass-12");
    expect((await screen.findByRole("status")).textContent).toContain("disabled");
  });

  it("signs up with name, email and password only, then says approval is needed", async () => {
    const api = gate();
    fireEvent.click(await screen.findByRole("button", { name: "Create one" }));
    const form = screen.getByRole("form", { name: "Create an account" });
    expect(form.querySelectorAll("input")).toHaveLength(4); // name, email, password twice: no role
    expect(form.querySelector("select")).toBeNull();
    fill("Name", "Kim Lee");
    fill("Email", "kim@example.test");
    fill("Password", "kim-pass-12");
    fill("Password again", "kim-pass-12");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect((await screen.findByRole("status")).textContent).toContain("must approve it");
    expect(api.users.find((u) => u.email === "kim@example.test")).toMatchObject({ status: "pending", role: "viewer" });
  });

  it("checks the two passwords before signing up", async () => {
    const api = gate();
    fireEvent.click(await screen.findByRole("button", { name: "Create one" }));
    fill("Name", "Kim Lee");
    fill("Email", "kim@example.test");
    fill("Password", "kim-pass-12");
    fill("Password again", "kim-pass-13");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect((await screen.findByRole("alert")).textContent).toContain("differ");
    expect(api.users).toHaveLength(USERS.length);
  });

  it("asks for the first admin on first run, with an email field only when none is configured", async () => {
    gate(createFakeAuthApi({ setup: "needs_admin" }));
    const form = await screen.findByRole("form", { name: "Create the administrator account" });
    expect(form.querySelector('input[type="email"]')).toBeNull();
    cleanupAndRender(createFakeAuthApi({ setup: "needs_admin_email" }));
    const withEmail = await screen.findByRole("form", { name: "Create the administrator account" });
    expect(withEmail.querySelector('input[type="email"]')).not.toBeNull();
  });

  it("does not offer first-run setup from a remote PC", async () => {
    render(
      <LoginGate api={createFakeAuthApi({ setup: "needs_admin" })} pollMs={0} local={false}>
        <App />
      </LoginGate>,
    );
    expect((await screen.findByRole("status")).textContent).toContain("on the microscope PC");
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("keeps the app mounted and Abort live while locked, and unlocks with the password", async () => {
    const onAbort = vi.fn();
    const api = gate(undefined, <button onClick={onAbort}>Abort</button>);
    await screen.findByRole("form", { name: "Log in" });
    await logIn("otto@example.test", "otto-pass-1");
    await screen.findByText("the app for Otto Operator");
    fireEvent.click(screen.getByRole("button", { name: "Lock" }));
    await screen.findByRole("dialog", { name: "Locked" });
    // the app is still there underneath (work goes on), but cannot be used
    const app = screen.getByText("the app for Otto Operator", { selector: "p" }).closest("[inert]");
    expect(app).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Abort" }));
    expect(onAbort).toHaveBeenCalledOnce();
    fill("Password", "wrong-pass");
    fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Wrong password");
    fill("Password", "otto-pass-1");
    fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Locked" })).toBeNull());
    expect(await api.me()).toMatchObject({ locked: false });
  });

  it("picks up an idle lock from the server when it polls", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const api = createFakeAuthApi({ users: USERS });
      await api.login({ email: "otto@example.test", password: "otto-pass-1" });
      render(
        <LoginGate api={api} pollMs={1000}>
          <App />
        </LoginGate>,
      );
      await screen.findByText("the app for Otto Operator");
      api.lockNow();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByRole("dialog", { name: "Locked" })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("logs out back to the login form", async () => {
    const api = createFakeAuthApi({ users: USERS });
    await api.login({ email: "otto@example.test", password: "otto-pass-1" });
    gate(api);
    fireEvent.click(await screen.findByRole("button", { name: "Log out" }));
    await screen.findByRole("form", { name: "Log in" });
    expect(await api.me()).toBeNull();
  });
});

function cleanupAndRender(api: ReturnType<typeof createFakeAuthApi>) {
  cleanup();
  render(
    <LoginGate api={api} pollMs={0}>
      <App />
    </LoginGate>,
  );
}

describe("ApprovalList", () => {
  const me = (over: Partial<Me>): Me => ({
    user_id: "admin@example.test",
    name: "Ada Admin",
    role: "admin",
    locked: false,
    has_control: false,
    local: true,
    expires_at: 0,
    ...over,
  });

  it("is hidden for a non-admin and for a remote admin", async () => {
    const api = createFakeAuthApi({ users: USERS });
    const pending = vi.spyOn(api, "pending");
    const { container, rerender } = render(<ApprovalList api={api} me={me({ role: "operator" })} />);
    expect(container.innerHTML).toBe("");
    rerender(<ApprovalList api={api} me={me({ local: false })} />);
    expect(container.innerHTML).toBe("");
    expect(pending).not.toHaveBeenCalled();
  });

  it("approves with a role the admin picks; there is no default role", async () => {
    const api = createFakeAuthApi({ users: USERS });
    await api.login({ email: "admin@example.test", password: "admin-pass-1" });
    render(<ApprovalList api={api} me={me({})} />);
    const picker = (await screen.findByLabelText("Role for pat@example.test")) as HTMLSelectElement;
    const approve = screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement;
    expect(picker.value).toBe("");
    expect(approve.disabled).toBe(true);
    fireEvent.change(picker, { target: { value: "operator" } });
    fireEvent.click(approve);
    await screen.findByText("No accounts are waiting.");
    expect(api.users.find((u) => u.email === "pat@example.test")).toMatchObject({ status: "active", role: "operator" });
  });
});

describe("LoginGate on a remote PC", () => {
  it("guesses remote from the page host and offers no first-run setup", async () => {
    const original = window.location;
    Object.defineProperty(window, "location", { configurable: true, value: { ...original, hostname: "lab-pc.example.test" } });
    try {
      render(
        <LoginGate api={createFakeAuthApi({ setup: "needs_admin" })} pollMs={0}>
          <App />
        </LoginGate>,
      );
      expect((await screen.findByRole("status")).textContent).toContain("on the microscope PC");
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: original });
    }
  });
});
