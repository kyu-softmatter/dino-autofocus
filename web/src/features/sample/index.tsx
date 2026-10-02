/**
 * `sample` area: samples and the loading check (PLAN F3; contract docs/screens/sample.md).
 *
 * Route rest: `?sample_id=<id>` views that sample; empty views the sample the
 * engine has open. Viewing is not opening: "Open" sends `sample_open`.
 *
 * The screen decides nothing: refusals come from the server (403 detail, the
 * access reasons) or the engine (`preflight_failed`), and the loading state
 * comes from the engine's sample view.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAreaPath } from "../../app/route";
import { useScreenContext } from "../../app/screenContext";
import {
  type CommandIn,
  type CurrentSample,
  type EventOut,
  type Geometry,
  type GeometryField,
  type LoadingState,
  type Permissions,
  SAMPLE_OPS,
  type SampleAccess,
  type SampleDetail,
  type SampleOp,
  type SampleSummary,
  type SendResult,
  useSampleApi,
} from "./api";
import { GeometryForm, LoadingCheck, Reason, SampleList, SampleSummaryPanel } from "./parts";
import "./sample.css";

function sampleIdOf(rest: string): string | null {
  const q = rest.startsWith("?") ? rest.slice(1) : rest;
  return new URLSearchParams(q).get("sample_id");
}

const isSampleOp = (op: unknown): op is SampleOp => (SAMPLE_OPS as readonly unknown[]).includes(op);

/** which control a command belongs to, so its refusal shows next to it */
function controlOf(cmd: CommandIn): string {
  switch (cmd.op) {
    case "sample_open":
      return `open:${String(cmd.args.sample_id)}`;
    case "sample_new":
      return "new";
    case "sample_geometry_set":
      return "geometry";
    case "loading_confirm_person":
      return "person";
    case "loading_check_image":
      return "image";
  }
}

interface Selected {
  detail: SampleDetail;
  geometry: Geometry;
  loading: LoadingState;
}

export default function SampleScreen() {
  const api = useSampleApi();
  const [rest, setRest] = useAreaPath();
  const [list, setList] = useState<SampleSummary[]>([]);
  const [fields, setFields] = useState<GeometryField[]>([]);
  const [current, setCurrent] = useState<CurrentSample | null>(null);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [access, setAccess] = useState<SampleAccess | null>(null);
  const [perms, setPerms] = useState<Permissions>({});
  const [error, setError] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [imageStatus, setImageStatus] = useState<string | null>(null);
  const [light, setLight] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // bump to re-read everything
  const pending = useRef(new Map<string, string>()); // op_id -> control

  const viewId = sampleIdOf(rest) ?? current?.sample_id ?? null;
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let live = true;
    Promise.all([api.list(), api.fields(), api.current()])
      .then(([l, f, c]) => {
        if (!live) return;
        setList(l);
        setFields(f);
        setCurrent(c);
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [api, tick]);

  useEffect(() => {
    let live = true;
    Promise.all([api.access(viewId), api.permissions(SAMPLE_OPS)])
      .then(([a, p]) => {
        if (!live) return;
        setAccess(a);
        setPerms(p);
      })
      .catch((e: Error) => live && setError(e.message));
    if (viewId === null) {
      setSelected(null);
      return () => {
        live = false;
      };
    }
    Promise.all([api.detail(viewId), api.geometry(viewId), api.loading(viewId)])
      .then(([detail, geometry, loading]) => live && setSelected({ detail, geometry, loading }))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [api, viewId, tick]);

  const setReason = useCallback((control: string, why: string | null) => {
    setReasons((r) => {
      const next = { ...r };
      if (why) next[control] = why;
      else delete next[control];
      return next;
    });
  }, []);

  const onEvent = useCallback(
    (ev: EventOut) => {
      const control = pending.current.get(ev.op_id);
      const op = ev.data.op;
      switch (ev.kind) {
        case "sample_opened":
          setRest("");
          refresh();
          return;
        case "map_changed":
          refresh();
          return;
        case "light_changed":
          setLight(typeof ev.data.dialamp === "string" ? ev.data.dialamp : null);
          return;
        case "preflight_failed":
          if (control) setReason(control, String(ev.data.why ?? "refused"));
          if (control === "image") setImageStatus(null);
          pending.current.delete(ev.op_id);
          return;
        case "started":
        case "progress":
          if (control === "image") setImageStatus(String(ev.data.status ?? "Checking…"));
          return;
        case "aborted":
        case "error":
          if (control) setReason(control, `stopped: ${String(ev.data.why ?? ev.data.message ?? "unknown")}`);
          if (control === "image") setImageStatus(null);
          pending.current.delete(ev.op_id);
          return;
        case "finished": {
          if (control === "image") setImageStatus(null);
          pending.current.delete(ev.op_id);
          if (!isSampleOp(op)) return;
          const summary = (ev.data.summary ?? {}) as { sample_id?: unknown };
          if (op === "sample_new" && typeof summary.sample_id === "string") {
            setRest(`?sample_id=${encodeURIComponent(summary.sample_id)}`);
          }
          refresh();
          return;
        }
      }
    },
    [refresh, setReason, setRest],
  );

  useEffect(() => api.subscribe(onEvent), [api, onEvent]);

  const send = useCallback(
    async (cmd: CommandIn) => {
      const control = controlOf(cmd);
      setReason(control, null);
      let res: SendResult;
      try {
        res = await api.send(cmd);
      } catch (e) {
        res = { ok: false, reason: (e as Error).message };
      }
      if (res.ok) pending.current.set(res.op_id, control);
      else setReason(control, res.reason);
    },
    [api, setReason],
  );

  const openFolder = useCallback(async () => {
    if (!selected) return;
    const res = await api.openFolder(selected.detail.sample_id);
    setReason("folder", res.ok ? null : res.reason);
  }, [api, selected, setReason]);

  // the shared verdict first (ui-spec 7.0 order is the server's), then the sample-specific one
  const denied = (op: SampleOp): string | null => {
    const p = perms[op];
    return p && !p.allowed ? (p.reason ?? `${op} is not allowed now`) : null;
  };
  const openBlocked = denied("sample_open") ?? access?.open_reason ?? null;
  const newBlocked = denied("sample_new") ?? access?.open_reason ?? null;
  const id = selected?.detail.sample_id ?? null;

  const details = useMemo(() => {
    if (!selected) return {};
    const geometry = Object.fromEntries(
      Object.entries(selected.geometry.values).map(([k, v]) => [k, { value: v.value, source: v.source.kind }]),
    );
    const l = selected.loading;
    return {
      sample_id: selected.detail.sample_id,
      geometry,
      loading: { geometry: l.geometry.done, person: l.person.done, image: l.image.done && l.image.ok === true, confirmed: l.confirmed },
    };
  }, [selected]);
  useScreenContext(details);

  return (
    <div className="sample-screen">
      <h2>Sample</h2>
      {error && (
        <p className="sample-reason" role="alert">
          {error}
        </p>
      )}
      <section aria-label="Samples" className="sample-panel">
        <h3>Samples</h3>
        <p>
          <button disabled={newBlocked !== null} onClick={() => void send({ kind: "start", op: "sample_new", args: {} })}>
            New sample
          </button>
          <Reason text={newBlocked ?? reasons.new} />
        </p>
        <SampleList
          samples={list}
          currentId={current?.sample_id ?? null}
          selectedId={id}
          onView={(sid) => setRest(`?sample_id=${encodeURIComponent(sid)}`)}
          onOpen={(sid) => void send({ kind: "start", op: "sample_open", args: { sample_id: sid } })}
          openBlocked={openBlocked}
          reasons={reasons}
        />
      </section>
      {selected && id && (
        <>
          <SampleSummaryPanel
            detail={selected.detail}
            canOpenFolder={access?.can_open_folder === true}
            onOpenFolder={() => void openFolder()}
            folderReason={reasons.folder}
          />
          <GeometryForm
            fields={fields}
            geometry={selected.geometry}
            blocked={denied("sample_geometry_set")}
            reason={reasons.geometry}
            onSave={(values) => void send({ kind: "start", op: "sample_geometry_set", args: { sample_id: id, values } })}
          />
          <LoadingCheck
            loading={selected.loading}
            personBlocked={denied("loading_confirm_person")}
            imageBlocked={denied("loading_check_image")}
            reasons={reasons}
            imageStatus={imageStatus}
            onPerson={() => void send({ kind: "start", op: "loading_confirm_person", args: { sample_id: id } })}
            onImage={() => void send({ kind: "start", op: "loading_check_image", args: { sample_id: id } })}
          />
          {light && <p className="muted">Brightfield: {light}</p>}
        </>
      )}
      {!selected && <p className="muted">No sample selected. Pick one from the list or make a new one.</p>}
    </div>
  );
}
