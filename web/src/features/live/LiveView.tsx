import { useEffect, useRef, useState } from "react";

import { useClient } from "../../app/client";
import { EncoderZ } from "../../app/Verdict";
import { FpsMeter, type FrameMeta, FramePairer } from "./frames";

type Conn = "connecting" | "open" | "closed" | "unsupported";

const RETRY_MS = 2000;

// a module constant: a new default function on every render would reconnect each time
const performanceNow = () => performance.now();

/**
 * The live view: the server bins each camera frame to about 800 px and sends it
 * as JPEG (T-009 /ws/frames, about 10 fps). Shows the frame, its time and the
 * receive rate. Display only: raw frames stay on disk.
 */
export function LiveView({ now = performanceNow }: { now?: () => number }) {
  const client = useClient();
  const [url, setUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<FrameMeta | null>(null);
  const [fps, setFps] = useState<number | null>(null);
  const [conn, setConn] = useState<Conn>("connecting");
  const [detail, setDetail] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    let live = true;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let unsupported = false; // the engine has no frames: do not retry
    const pairer = new FramePairer();
    const meter = new FpsMeter();

    const connect = () => {
      if (!live) return;
      setConn("connecting");
      const ws = client.transport.openSocket("/ws/frames");
      socket = ws;
      ws.binaryType = "blob";
      ws.onopen = () => live && setConn("open");
      ws.onmessage = (msg) => {
        if (!live) return;
        const got = pairer.feed(msg.data);
        if (!got) return;
        if (got.kind === "error") {
          setDetail(got.detail);
          if (got.status === 501) {
            unsupported = true;
            setConn("unsupported");
          }
          return;
        }
        const next = URL.createObjectURL(got.jpeg);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = next;
        setUrl(next);
        setMeta(got.meta);
        setFps(meter.tick(now()));
      };
      ws.onclose = () => {
        socket = null;
        if (!live || unsupported) return;
        setConn("closed");
        timer = setTimeout(connect, RETRY_MS);
      };
    };
    connect();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
      socket?.close();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
  }, [client, now]);

  const frameTime = meta ? new Date(meta.t * 1000).toLocaleTimeString() : "—";
  const z = meta?.meta && typeof meta.meta.z_um === "number" ? (meta.meta.z_um as number) : null;

  return (
    <div className="live">
      <div className="live-info" data-testid="live-info">
        <span data-testid="live-conn">
          {conn === "open" ? "frames: connected" : conn === "unsupported" ? "frames: not available" : `frames: ${conn}`}
        </span>
        <span data-testid="live-time">frame {frameTime}</span>
        <span data-testid="live-fps">{fps === null ? "— fps" : `${fps.toFixed(1)} fps`}</span>
        {meta && (
          <span className="muted" data-testid="live-size">
            #{meta.seq} · {meta.width}×{meta.height} (bin {meta.binning} of {meta.source_width}×{meta.source_height}) ·
            display {meta.display_min.toFixed(0)}–{meta.display_max.toFixed(0)} counts
          </span>
        )}
        {z !== null && (
          <span
            data-testid="live-z"
            title="ZDrive encoder read when the frame was taken from the camera buffer; it can lag the exposure"
          >
            <EncoderZ readbackUm={z} />
          </span>
        )}
      </div>
      {detail && conn === "unsupported" && <p className="muted">{detail}</p>}
      {url ? (
        <img className="live-frame" src={url} alt="Live camera frame" />
      ) : (
        <p className="muted">No frame yet.</p>
      )}
    </div>
  );
}
