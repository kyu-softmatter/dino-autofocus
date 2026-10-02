# T-040 Spec nits (docs only)

- Owner: AF 실행17
- Branch: `exec17/T-040-spec-nits`
- Review: AF 검토보조2
- From BACKLOG "후속 과제 후보" (collected nits, each decided earlier).

## Owned paths

- `docs/operations-spec.md`, `docs/ui-spec.md` (the lines below only)

## Content

- operations-spec: the F5 step-out is decided: +Y, 15 mm, "unmeasured provisional" (PLAN v1.3, fbc1e08); say so where
  `escape_dy_um` is described. The `focus_100x` exposure default is 20 ms, provisional (2026-09-30, one run; T-031b).
- ui-spec: the image check grade is "computed", not "classical". The 4.0 transport row still calls abort open;
  D13 decided it (loopback abort and lights_off open; remote abort needs a login). `update` stays in the command table.
- Keep the Korean prose style of each file; change only these points.

## Done when

- Docs only, no tests. Send `[검토요청 T-040]` to AF 검토보조2. Trailer `Session: AF 실행17`.
