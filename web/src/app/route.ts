import { useCallback, useEffect, useState } from "react";

import { type AreaId, DEFAULT_AREA, isAreaId } from "./areas";

/** `#/map` -> "map". Hash routing: FastAPI serves one index.html, no server routes needed. */
export function areaFromHash(hash: string): AreaId {
  const id = hash.replace(/^#\/?/, "").split(/[/?]/)[0];
  return isAreaId(id) ? id : DEFAULT_AREA;
}

export function hashOfArea(id: AreaId): string {
  return `#/${id}`;
}

export function useArea(): [AreaId, (id: AreaId) => void] {
  const [area, setArea] = useState<AreaId>(() => areaFromHash(window.location.hash));
  useEffect(() => {
    const onHash = () => setArea(areaFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = useCallback((id: AreaId) => {
    window.location.hash = hashOfArea(id);
    setArea(id);
  }, []);
  return [area, go];
}
