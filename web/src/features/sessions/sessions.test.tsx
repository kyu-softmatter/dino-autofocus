import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ScreenContextProvider } from "../../app/screenContext";
import { createFakeClient, denyAll, fakeDetail, type SessionsClient, SessionsClientContext } from "./api";
import SessionsScreen from "./index";

const CLOSED = fakeDetail({
  session_id: "20261001-0905-operator-1",
  sample_id: "20260930_1849_1",
  code: { repo: "r", commit: "abcdef1234567890".padEnd(40, "0"), dirty: true, error: null },
  hardware_profile: { path: "hardware_profile.json", sha256: "1234567890ab".padEnd(64, "f") },
  records: [{ name: "scan_4x.jsonl", lines: 5 }],
  manifest: { files: 2, bytes: 11_520_100, by_where: { data: 1, session: 1 }, entries: [] },
  log_tail: [{ t: "2026-10-01T09:05:00-07:00", level: "info", msg: "session opened" }],
  reflected: true,
});


function show(client: SessionsClient, hash = "#/sessions") {
  window.location.hash = hash;
  return render(
    <SessionsClientContext.Provider value={client}>
      <ScreenContextProvider area="sessions">
        <SessionsScreen />
      </ScreenContextProvider>
    </SessionsClientContext.Provider>,
  );
}

const button = (name: RegExp | string) => screen.getByRole("button", { name }) as HTMLButtonElement;

describe("sessions screen", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("lists sessions and shows a detail as recorded", async () => {
    show(createFakeClient({ sessions: [CLOSED] }), `#/sessions/${CLOSED.session_id}`);
    const table = await screen.findByRole("table", { name: "Sessions" });
    await within(table).findByText(CLOSED.session_id);
    const detail = await screen.findByRole("article", { name: "Session detail" });
    expect(within(detail).getByText("abcdef123456")).toBeTruthy(); // code commit, as recorded
    expect(within(detail).getByText(/uncommitted changes/)).toBeTruthy();
    expect(within(detail).getByText("1234567890ab")).toBeTruthy(); // hardware sha256
    expect(within(detail).getByText("scan_4x.jsonl: 5 lines")).toBeTruthy();
    expect(screen.getByTestId("current").textContent).toBe("No experiment session");
  });

  it("filters the list by status", async () => {
    const open = fakeDetail({ session_id: "s-open", sample_id: "x", status: "open", closed_at: null });
    show(createFakeClient({ sessions: [CLOSED, open] }));
    await screen.findByText("s-open");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "closed" } });
    await waitFor(() => expect(screen.queryByText("s-open")).toBeNull());
    expect(screen.getByText(CLOSED.session_id)).toBeTruthy();
  });

  it("opens a session for the current sample and closes it", async () => {
    show(createFakeClient({ currentSample: "20260930_1849_1" }));
    const open = await waitFor(() => {
      const b = button("Open experiment session for 20260930_1849_1");
      expect(b.disabled).toBe(false);
      return b;
    });
    await act(async () => fireEvent.click(open));
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("Open: fake-1 · 20260930_1849_1"));
    expect(button(/Open experiment session/).disabled).toBe(true);
    expect(screen.getByText("fake-1 is open; close it first")).toBeTruthy();
    expect(window.location.hash).toBe("#/sessions/fake-1");

    fireEvent.change(await screen.findByLabelText("Note"), { target: { value: "done" } });
    await act(async () => fireEvent.click(button("Close")));
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("No experiment session"));
    expect(button("Close").disabled).toBe(true);
    expect(screen.getByText("Session fake-1 is closed (read-only)")).toBeTruthy();
  });

  it("says why opening is off when no sample is current", async () => {
    show(createFakeClient({ currentSample: null }));
    await waitFor(() => expect(screen.getByText("Open or create a sample first")).toBeTruthy());
    expect(button("Open experiment session").disabled).toBe(true);
  });

  it("continues a closed session with the same sample", async () => {
    show(createFakeClient({ sessions: [CLOSED] }), `#/sessions/${CLOSED.session_id}`);
    const cont = await waitFor(() => {
      const b = button("Continue with this sample");
      expect(b.disabled).toBe(false);
      return b;
    });
    await act(async () => fireEvent.click(cont));
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe(`Open: fake-1 · ${CLOSED.sample_id}`));
    const detail = await screen.findByRole("article", { name: "Session detail" });
    await within(detail).findByText("fake-1");
    expect(within(detail).getAllByText(CLOSED.session_id).length).toBeGreaterThan(0); // continues
  });

  it("is read-only for a remote viewer, with the reason shown", async () => {
    const open = fakeDetail({ session_id: "s-open", sample_id: "x", status: "open", closed_at: null });
    show(createFakeClient({ sessions: [CLOSED, open], currentSample: "x", permission: denyAll("Read-only: remote view") }), "#/sessions/s-open");
    await screen.findByRole("article", { name: "Session detail" });
    await waitFor(() => expect(button("Close").disabled).toBe(true));
    expect(button(/Open experiment session/).disabled).toBe(true);
    expect(button("Continue with this sample").disabled).toBe(true);
    expect(screen.getAllByText("Read-only: remote view").length).toBeGreaterThanOrEqual(3);
  });

  it("refuses closing someone else's session with the router's reason", async () => {
    const other = fakeDetail({
      session_id: "s-other",
      sample_id: "x",
      status: "open",
      closed_at: null,
      user_id: "second@example.test",
    });
    show(createFakeClient({ sessions: [other] }), "#/sessions/s-other");
    await screen.findByRole("article", { name: "Session detail" });
    const close = await waitFor(() => {
      const b = button("Close");
      expect(b.disabled).toBe(false); // ownership is the router's 403, not a screen rule
      return b;
    });
    await act(async () => fireEvent.click(close));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Only second@example.test or an admin can close this session",
    );
  });
});
