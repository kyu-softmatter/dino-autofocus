import { defaultApi } from "./api";
import { ObjectiveView } from "./ObjectiveView";

/** Area screen for `objective` (web/README.md: default export, no props). */
export default function ObjectiveScreen() {
  return <ObjectiveView api={defaultApi} />;
}
