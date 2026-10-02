"""Console area (PLAN.md F1, ui-spec 7.1, docs/screens/console.md): the agents' questions, runs
and inbox, read from the AgentStore, and the one write, a question to the mock store.

The router reads only. Whether someone may submit is not decided here: the access middleware
already refuses a remote or logged-out write, and the route asks `server_action_why` for the
T-018 permission `SUBMIT_QUESTION` (operator on the microscope PC, D16). The console's own rule
is the read-only store (409). Records pass through as the store has them: card contents,
grades and `numbers` are not touched (PLAN.md 6절 3항).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...agents import AGENTS, MockStore, NotFoundError, ReadOnlyStoreError, StoreError
from ...auth import AuditKind
from . import AgentStoreDep, Auth, Login, Refusal, Sessions, server_action_why

router = APIRouter()

AgentName = Literal["microscope", "simulation"]
READ_ONLY_MESSAGE = "Submitting to soft-matter-agents is not connected yet (read-only)"


# -- wire models (the AgentStore records' to_dict() shapes) -------------------------------


class FileInfoOut(BaseModel):
    name: str
    size: int | None


class CardOut(BaseModel):
    name: str
    kind: str
    version: int
    status: str | None
    created_at: str | None
    data: Any = Field(description="the card file's content, untouched")


class DocumentOut(BaseModel):
    name: str
    version: int
    text: str


class QuestionSummaryOut(BaseModel):
    qid: str
    agent: AgentName
    title: str
    status: str | None
    created_at: str | None
    updated_at: str | None
    latest_version: int
    versions: list[int]
    source: str
    purpose: str | None = None
    intent: str | None = None
    observable_name: str | None = None


class QuestionDetailOut(BaseModel):
    summary: QuestionSummaryOut
    version: int
    goal: CardOut | None
    axes: list[CardOut]
    plan: CardOut | None
    synthesis: CardOut | None
    refusals: list[CardOut]
    results: list[CardOut]
    others: list[CardOut]
    documents: list[DocumentOut]
    files: list[FileInfoOut]


class RunSummaryOut(BaseModel):
    run_id: str
    agent: AgentName
    qid: str | None
    plan_id: str | None
    status: str | None
    created_at: str | None
    finished_at: str | None
    backend: str | None
    source: str
    approval_kind: str | None = None


class RunDetailOut(BaseModel):
    summary: RunSummaryOut
    records: dict[str, Any] = Field(description="file name -> content, untouched")
    files: list[FileInfoOut]
    not_opened: list[str]


class InboxMessageOut(BaseModel):
    name: str
    round: int | None
    kind: str
    card: Any
    text: str | None


class InboxThreadOut(BaseModel):
    thread: str
    agent: AgentName | None
    state: str | None
    turn: str | None
    round: int | None
    updated_at: str | None
    status: Any
    messages: list[InboxMessageOut]
    source: str


class StoreOut(BaseModel):
    store: str = Field(description='"mock" or "soft-matter-agents"')
    writable: bool


class QuestionIn(BaseModel):
    text: str
    target: AgentName
    purpose: str | None = None
    observable: str | None = None


# -- refusals -----------------------------------------------------------------------------


def _not_found(e: NotFoundError) -> Refusal:
    return Refusal(404, "not_found", str(e))


def _invalid(e: ValueError) -> Refusal:
    return Refusal(422, "invalid", str(e))


READ_ONLY = Refusal(409, "read_only_store", READ_ONLY_MESSAGE)

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "no such question, version or run"},
    500: {"description": "the store could not read the files"},
}


def _store_error(e: StoreError) -> Refusal:
    return Refusal(500, "store_error", str(e))


def _newest_first(items: list[Any]) -> list[Any]:
    return sorted(items, key=lambda x: (x.created_at or "", getattr(x, "qid", None) or
                                        getattr(x, "run_id", "")), reverse=True)


def _agents(agent: AgentName | None) -> tuple[str, ...]:
    return AGENTS if agent is None else (agent,)


# -- routes -------------------------------------------------------------------------------


@router.get("/store", response_model=StoreOut)
def store_info(store: AgentStoreDep) -> StoreOut:
    """Which store is behind the console, and whether a question can be submitted to it."""
    if isinstance(store, MockStore):
        name = "mock"
    else:
        name = getattr(store, "source", "soft-matter-agents")
    return StoreOut(store=name, writable=bool(store.writable))


@router.get("/questions", response_model=list[QuestionSummaryOut], responses=ERRORS)
def list_questions(store: AgentStoreDep,
                   agent: AgentName | None = None) -> list[QuestionSummaryOut]:
    """Both agents' questions, newest first, unless `agent` names one."""
    try:
        found = [q for a in _agents(agent) for q in store.list_questions(a)]
    except StoreError as e:
        raise _store_error(e).http() from e
    return [QuestionSummaryOut.model_validate(q.to_dict()) for q in _newest_first(found)]


@router.get("/questions/{qid}", response_model=QuestionDetailOut, responses=ERRORS)
def get_question(qid: str, store: AgentStoreDep, version: int | None = None) -> QuestionDetailOut:
    """One version of a question (the latest unless `version` is given)."""
    try:
        d = store.get_question(qid, version)
    except NotFoundError as e:
        raise _not_found(e).http() from e
    except StoreError as e:
        raise _store_error(e).http() from e
    return QuestionDetailOut.model_validate(d.to_dict())


@router.get("/runs", response_model=list[RunSummaryOut], responses=ERRORS)
def list_runs(store: AgentStoreDep, agent: AgentName | None = None) -> list[RunSummaryOut]:
    try:
        found = [r for a in _agents(agent) for r in store.list_runs(a)]
    except StoreError as e:
        raise _store_error(e).http() from e
    return [RunSummaryOut.model_validate(r.to_dict()) for r in _newest_first(found)]


@router.get("/runs/{agent}/{run_id}", response_model=RunDetailOut, responses=ERRORS)
def get_run(agent: AgentName, run_id: str, store: AgentStoreDep) -> RunDetailOut:
    try:
        r = store.get_run(agent, run_id)
    except NotFoundError as e:
        raise _not_found(e).http() from e
    except StoreError as e:
        raise _store_error(e).http() from e
    return RunDetailOut.model_validate(r.to_dict())


@router.get("/inbox", response_model=list[InboxThreadOut], responses=ERRORS)
def list_inbox(store: AgentStoreDep) -> list[InboxThreadOut]:
    try:
        threads = store.list_inbox()
    except StoreError as e:
        raise _store_error(e).http() from e
    return [InboxThreadOut.model_validate(t.to_dict()) for t in threads]


@router.post(
    "/questions",
    status_code=201,
    response_model=QuestionSummaryOut,
    responses={403: {"description": "remote view or role (D16)"},
               409: {"description": "the store is read-only"},
               422: {"description": "empty text, unknown purpose"}},
)
def submit_question(body: QuestionIn, store: AgentStoreDep, me: Login, seat: Auth,
                    sessions: Sessions) -> QuestionSummaryOut:
    """Leave a question for a seat. The mock store only; operator on the microscope PC (D16)."""
    if why := server_action_why(me, "submit_question"):
        raise why.http()
    if not store.writable:
        raise READ_ONLY.http()
    try:
        q = store.submit_question(body.text, body.target, purpose=body.purpose,
                                  observable=body.observable)
    except ReadOnlyStoreError as e:
        raise READ_ONLY.http() from e
    except ValueError as e:
        raise _invalid(e).http() from e
    except StoreError as e:
        raise _store_error(e).http() from e
    if seat.audit is not None:
        cur = sessions.current
        seat.audit.append(AuditKind.QUESTION_SUBMITTED, me.user_id,
                          session_id=cur.info.session_id if cur is not None else None,
                          origin="console", target=body.target, qid=q.qid)
    return QuestionSummaryOut.model_validate(q.to_dict())
