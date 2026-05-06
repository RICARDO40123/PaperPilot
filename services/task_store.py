"""In-memory job store for async analyze tasks (dev-friendly; not multi-process safe)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from models.analysis import AnalyzeRequest, AnalyzeResponse
from models.reading_api import (
    ReadingAdviseRequest,
    RecommendReadingRequest,
    StructureIntentRequest,
)
from models.translate import TranslateRequest, TranslateResponse

JOB_TTL_SECONDS = 30 * 60
MAX_CONCURRENT_ANALYZE = 2
MAX_CONCURRENT_TRANSLATE = 2
MAX_CONCURRENT_READING = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _age_seconds(created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (_utc_now() - created_at).total_seconds()


@dataclass
class AnalyzeJobRecord:
    job_id: str
    request: AnalyzeRequest
    status: str  # queued | running | done | failed
    progress: int = 0
    result: AnalyzeResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


class AnalyzeJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, AnalyzeJobRecord] = {}
        self._concurrency = threading.Semaphore(MAX_CONCURRENT_ANALYZE)

    def acquire_concurrency_slot(self, blocking: bool = True, timeout: float | None = None) -> bool:
        if timeout is None:
            return self._concurrency.acquire(blocking=blocking)
        return self._concurrency.acquire(blocking=blocking, timeout=timeout)

    def release_concurrency_slot(self) -> None:
        self._concurrency.release()

    def _cleanup_unlocked(self) -> None:
        to_del = [
            jid
            for jid, rec in self._jobs.items()
            if _age_seconds(rec.created_at) > JOB_TTL_SECONDS
        ]
        for jid in to_del:
            del self._jobs[jid]

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_unlocked()

    def submit(self, req: AnalyzeRequest) -> str:
        self.cleanup()
        job_id = str(uuid.uuid4())
        rec = AnalyzeJobRecord(job_id=job_id, request=req, status="queued", progress=0)
        with self._lock:
            self._jobs[job_id] = rec
        return job_id

    def get(self, job_id: str) -> AnalyzeJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: int | None = None,
        result: AnalyzeResponse | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.status = status
            if progress is not None:
                rec.progress = progress
            if result is not None:
                rec.result = result
            if error is not None:
                rec.error = error


analyze_job_store = AnalyzeJobStore()


def _run_analyze_job(job_id: str) -> None:
    from services.analyze_pipeline import run_analyze

    store = analyze_job_store
    rec = store.get(job_id)
    if not rec:
        return

    store.update_status(job_id, "queued", progress=0)
    if not store.acquire_concurrency_slot(blocking=True):
        store.update_status(job_id, "failed", error="无法获取分析并发槽位")
        return
    try:
        store.update_status(job_id, "running", progress=10)
        resp = run_analyze(rec.request)
        store.update_status(job_id, "done", progress=100, result=resp)
    except Exception as e:  # noqa: BLE001
        store.update_status(job_id, "failed", progress=0, error=str(e))
    finally:
        store.release_concurrency_slot()


def start_analyze_job(job_id: str) -> None:
    t = threading.Thread(target=_run_analyze_job, args=(job_id,), daemon=True)
    t.start()


# --- Translate jobs ---


@dataclass
class TranslateJobRecord:
    job_id: str
    request: TranslateRequest
    status: str
    progress: int = 0
    result: TranslateResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


class TranslateJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, TranslateJobRecord] = {}
        self._concurrency = threading.Semaphore(MAX_CONCURRENT_TRANSLATE)

    def acquire_concurrency_slot(self, blocking: bool = True, timeout: float | None = None) -> bool:
        if timeout is None:
            return self._concurrency.acquire(blocking=blocking)
        return self._concurrency.acquire(blocking=blocking, timeout=timeout)

    def release_concurrency_slot(self) -> None:
        self._concurrency.release()

    def _cleanup_unlocked(self) -> None:
        to_del = [
            jid
            for jid, rec in self._jobs.items()
            if _age_seconds(rec.created_at) > JOB_TTL_SECONDS
        ]
        for jid in to_del:
            del self._jobs[jid]

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_unlocked()

    def submit(self, req: TranslateRequest) -> str:
        self.cleanup()
        job_id = str(uuid.uuid4())
        rec = TranslateJobRecord(job_id=job_id, request=req, status="queued", progress=0)
        with self._lock:
            self._jobs[job_id] = rec
        return job_id

    def get(self, job_id: str) -> TranslateJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: int | None = None,
        result: TranslateResponse | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.status = status
            if progress is not None:
                rec.progress = progress
            if result is not None:
                rec.result = result
            if error is not None:
                rec.error = error


translate_job_store = TranslateJobStore()


def _run_translate_job(job_id: str) -> None:
    from services.translate_core import translate_to_zh

    store = translate_job_store
    rec = store.get(job_id)
    if not rec:
        return

    store.update_status(job_id, "queued", progress=0)
    if not store.acquire_concurrency_slot(blocking=True):
        store.update_status(job_id, "failed", error="无法获取翻译并发槽位")
        return
    try:
        store.update_status(job_id, "running", progress=10)
        zh = translate_to_zh(rec.request)
        store.update_status(job_id, "done", progress=100, result=TranslateResponse(zh=zh))
    except Exception as e:  # noqa: BLE001
        store.update_status(job_id, "failed", progress=0, error=str(e))
    finally:
        store.release_concurrency_slot()


def start_translate_job(job_id: str) -> None:
    t = threading.Thread(target=_run_translate_job, args=(job_id,), daemon=True)
    t.start()


# --- Reading jobs (精读) ---


@dataclass
class ReadingJobRecord:
    job_id: str
    kind: str  # structure | recommend | advise
    structure_body: StructureIntentRequest | None = None
    recommend_body: RecommendReadingRequest | None = None
    advise_body: ReadingAdviseRequest | None = None
    status: str = "queued"
    progress: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


class ReadingJobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ReadingJobRecord] = {}
        self._concurrency = threading.Semaphore(MAX_CONCURRENT_READING)

    def acquire_concurrency_slot(self, blocking: bool = True, timeout: float | None = None) -> bool:
        if timeout is None:
            return self._concurrency.acquire(blocking=blocking)
        return self._concurrency.acquire(blocking=blocking, timeout=timeout)

    def release_concurrency_slot(self) -> None:
        self._concurrency.release()

    def _cleanup_unlocked(self) -> None:
        to_del = [
            jid
            for jid, rec in self._jobs.items()
            if _age_seconds(rec.created_at) > JOB_TTL_SECONDS
        ]
        for jid in to_del:
            del self._jobs[jid]

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_unlocked()

    def submit_structure(self, body: StructureIntentRequest) -> str:
        self.cleanup()
        job_id = str(uuid.uuid4())
        rec = ReadingJobRecord(
            job_id=job_id,
            kind="structure",
            structure_body=body,
            status="queued",
        )
        with self._lock:
            self._jobs[job_id] = rec
        return job_id

    def submit_recommend(self, body: RecommendReadingRequest) -> str:
        self.cleanup()
        job_id = str(uuid.uuid4())
        rec = ReadingJobRecord(
            job_id=job_id,
            kind="recommend",
            recommend_body=body,
            status="queued",
        )
        with self._lock:
            self._jobs[job_id] = rec
        return job_id

    def submit_advise(self, body: ReadingAdviseRequest) -> str:
        self.cleanup()
        job_id = str(uuid.uuid4())
        rec = ReadingJobRecord(
            job_id=job_id,
            kind="advise",
            advise_body=body,
            status="queued",
        )
        with self._lock:
            self._jobs[job_id] = rec
        return job_id

    def get(self, job_id: str) -> ReadingJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: int | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return
            rec.status = status
            if progress is not None:
                rec.progress = progress
            if result is not None:
                rec.result = result
            if error is not None:
                rec.error = error


reading_job_store = ReadingJobStore()


def _run_reading_job(job_id: str) -> None:
    from services.reading_pipeline import recommend_deep_read, run_pipeline, structure_user_intent

    store = reading_job_store
    rec = store.get(job_id)
    if not rec:
        return

    store.update_status(job_id, "queued", progress=0)
    if not store.acquire_concurrency_slot(blocking=True):
        store.update_status(job_id, "failed", error="无法获取精读任务并发槽位")
        return
    try:
        store.update_status(job_id, "running", progress=10)
        if rec.kind == "structure" and rec.structure_body:
            out = structure_user_intent(rec.structure_body.user_prompt)
            store.update_status(job_id, "done", progress=100, result=out.model_dump())
        elif rec.kind == "recommend" and rec.recommend_body:
            b = rec.recommend_body
            rec_obj, used = recommend_deep_read(
                b.structured_intent,
                b.paper_text,
                b.max_paper_chars,
            )
            store.update_status(
                job_id,
                "done",
                progress=100,
                result={
                    "recommendation": rec_obj.model_dump(),
                    "paper_chars_used": used,
                },
            )
        elif rec.kind == "advise" and rec.advise_body:
            b = rec.advise_body
            pipe = run_pipeline(
                b.user_prompt,
                paper_text=b.paper_text,
                max_paper_chars=b.max_paper_chars,
            )
            store.update_status(
                job_id,
                "done",
                progress=100,
                result=pipe.model_dump(),
            )
        else:
            store.update_status(job_id, "failed", error="任务载荷无效")
    except Exception as e:  # noqa: BLE001
        store.update_status(job_id, "failed", progress=0, error=str(e))
    finally:
        store.release_concurrency_slot()


def start_reading_job(job_id: str) -> None:
    t = threading.Thread(target=_run_reading_job, args=(job_id,), daemon=True)
    t.start()
