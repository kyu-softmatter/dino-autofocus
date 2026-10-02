"""Login sessions: tokens, pending notice, idle lock and unlock, expiry, role changes apply."""

from dino_autofocus.auth import LoginOutcome, Role


def test_login_issues_a_token_and_logout_ends_it(logins, seed_password, audit):
    r = logins.login("Otto@Example.test", seed_password)
    assert r.ok and r.token and r.info.user_id == "otto@example.test"
    assert r.info.role is Role.OPERATOR and not r.info.locked
    assert logins.get(r.token).login_id == r.info.login_id
    assert logins.logout(r.token) and logins.get(r.token) is None
    kinds = [e["kind"] for e in audit.entries()]
    assert "login" in kinds and "logout" in kinds
    assert all(r.token not in str(e) for e in audit.entries())


def test_failures_say_why_without_a_token(logins, seed_password, audit):
    bad = logins.login("otto@example.test", "wrong-pass")
    assert bad.outcome is LoginOutcome.BAD_CREDENTIALS and bad.token is None
    pending = logins.login("pat@example.test", seed_password)
    assert pending.outcome is LoginOutcome.PENDING and pending.token is None
    assert "approval" in pending.message
    failed = [e for e in audit.entries() if e["kind"] == "login_failed"]
    assert [e["reason"] for e in failed] == ["bad_credentials", "pending_approval"]


def test_idle_session_locks_and_unlocks_with_the_password(logins, login, clock, seed_password):
    token = login("otto@example.test")
    clock.advance(599)
    assert not logins.touch(token).locked  # input resets the idle timer
    clock.advance(599)
    assert not logins.get(token).locked
    clock.advance(1)
    assert logins.get(token).locked
    assert logins.touch(token).locked  # input on a locked screen does not unlock it
    assert logins.unlock(token, "wrong-pass") is None and logins.get(token).locked
    assert not logins.unlock(token, seed_password).locked


def test_manual_lock(logins, login):
    token = login("vera@example.test")
    assert logins.lock(token).locked


def test_session_expires_after_max_age_and_ends_listeners(logins, login, clock):
    ended = []
    logins.on_end(ended.append)
    token = login("otto@example.test")
    login_id = logins.get(token).login_id
    clock.advance(3600)
    assert logins.get(token) is None and ended == [login_id]


def test_role_change_applies_at_once_and_disabling_ends_the_session(logins, login, seeded):
    token = login("vera@example.test")
    seeded.set_role("admin@example.test", "vera@example.test", "operator")
    assert logins.get(token).role is Role.OPERATOR
    seeded.disable("admin@example.test", "vera@example.test")
    assert logins.get(token) is None


def test_unknown_token(logins):
    assert logins.get("not-a-token") is None and not logins.logout("not-a-token")
