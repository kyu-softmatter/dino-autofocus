"""Fixtures of the M1 mock bench (T-035). The helpers live in `e2e_helpers` (T-015d);
the names re-exported below keep in-flight branches that still import them by the old
module name working for one transition.

Memory (T-035b): numpy and scipy each bring an OpenBLAS that commits buffers for every CPU
thread on import, about 500 MiB each on this 16-thread desktop, which the whole e2e run then
carries. The mock renders with numpy and never needs threaded BLAS, so one thread is asked
for before anything imports numpy. This only takes effect when tests/e2e is collected first
(alone, or at the start of a run); a process that imported numpy earlier keeps its threads.
"""

from __future__ import annotations

import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

from collections.abc import Iterator  # noqa: E402 - after the thread limit above

import pytest  # noqa: E402
from e2e_helpers import (  # noqa: E402, F401 - re-export for one transition (T-015d)
    ENDS,
    OFF,
    OPERATOR,
    PASSWORD,
    USERS,
    Bench,
    SharedWorld,
    SimClock,
    after,
    engine_on,
    need,
    read_jsonl,
    records_store,
    stand_ins,
)

from dino_autofocus.auth import config as auth_config  # noqa: E402
from dino_autofocus.auth import passwords  # noqa: E402
from dino_autofocus.records import session as session_mod  # noqa: E402
from dino_autofocus.records.codeversion import CodeVersion  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _cheap_scrypt() -> Iterator[None]:
    """scrypt at the production cost takes ~0.4 s per hash; the bench hashes a few."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(passwords, "SCRYPT_N", 2**10)
        yield


@pytest.fixture(autouse=True)
def _no_real_settings(tmp_path, monkeypatch):
    """No test reads the real settings folder or admin email."""
    monkeypatch.setenv(auth_config.CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.delenv(auth_config.ADMIN_EMAIL_ENV, raising=False)


@pytest.fixture(scope="module")
def _shared(tmp_path_factory):
    """What the per-test benches of one module share: one records repository (one
    `git init`) and one mock world (one virtual sample). Each bench still has its own
    auth, runner, sample folder and experiment session."""
    return records_store(tmp_path_factory.mktemp("records")), SharedWorld()


@pytest.fixture
def bench(tmp_path, monkeypatch, _shared) -> Iterator[Bench]:
    """A fresh bench per test (the safety tests). The code version a session records is
    stubbed here (two git calls on this repository per session); the day keeps the real one."""
    store, world = _shared
    monkeypatch.setattr(session_mod, "code_version",
                        lambda repo=None: CodeVersion("e2e stub", "0" * 40, False))
    yield from engine_on(Bench(tmp_path / "bench", local_gone_abort_s=0.3, store=store,
                               world=world.fresh()))


@pytest.fixture(scope="module")
def day(tmp_path_factory) -> Iterator[Bench]:
    """One bench for a whole module: the steps of one day share it, in file order."""
    root = tmp_path_factory.mktemp("m1_day")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(auth_config.CONFIG_DIR_ENV, str(root / "config"))
        mp.delenv(auth_config.ADMIN_EMAIL_ENV, raising=False)
        b = Bench(root)
        b.done, b.trace = set(), None
        yield from engine_on(b)
