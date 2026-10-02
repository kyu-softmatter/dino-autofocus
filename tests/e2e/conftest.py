"""Fixtures of the M1 mock bench (T-035). The helpers live in `e2e_helpers` (T-015d);
the names re-exported below keep in-flight branches that still import them by the old
module name working for one transition."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from e2e_helpers import (  # noqa: F401 - re-export for one transition (T-015d)
    ENDS,
    OFF,
    OPERATOR,
    PASSWORD,
    USERS,
    Bench,
    SimClock,
    after,
    engine_on,
    need,
    read_jsonl,
    stand_ins,
)

from dino_autofocus.auth import config as auth_config
from dino_autofocus.auth import passwords


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


@pytest.fixture
def bench(tmp_path) -> Iterator[Bench]:
    """A fresh bench per test (the safety tests)."""
    yield from engine_on(Bench(tmp_path / "bench", local_gone_abort_s=0.3))


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
