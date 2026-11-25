import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from celery import Celery
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from .access import STAFF, current, fail, lesson_access, pub_access, required, roles
from .db import (
    ROOT,
    add,
    change,
    citations,
    jobs,
    log,
    now,
    papers,
    row,
    rows,
    settings,
    transaction,
    uid,
    users,
    versions,
)
from .generation import generate
from .practice import Analysis, Answer, analyze, grade
from .resources import Material, make_version

router = APIRouter(prefix="/api/jobs")
BROKER = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery = Celery("classroom", broker=BROKER)
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={"recover": {"task": "classroom.recover", "schedule": 60.0}},
)
pool = ThreadPoolExecutor(max_workers=3)
TERMINAL = {"完成", "失败", "已取消"}


class Generate(BaseModel):
    prompt: str = Field(min_length=1, max_length=2500)
    parent: str = ""


class Export(BaseModel):
    lesson: str
    format: str


class Stopped(Exception):
    pass


def render_export(key, payload):
    lesson = payload["snapshot"]
    folder = ROOT / "exports"
    folder.mkdir(exist_ok=True)
    form = payload["format"]
    target = folder / (key + "." + form)
    tmp = folder / (uid() + "." + form)
    blocks = [(section, part["text"]) for section, part in lesson["sections"].items()]
    blocks.append(("引用资源", "\n".join(payload["citations"]) or "无"))
    if form == "docx":
        from docx import Document

        doc = Document()
        doc.add_heading(lesson["title"], 0)
        doc.add_paragraph("备课版本 V" + str(lesson["rev"]))
        for title, body in blocks:
            doc.add_heading(title, 1)
            doc.add_paragraph(body)
        doc.save(tmp)
    else:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        head = ParagraphStyle(
            "head", fontName="STSong-Light", fontSize=17, leading=24, spaceAfter=9, wordWrap="CJK"
        )
        body = ParagraphStyle(
            "body", fontName="STSong-Light", fontSize=11, leading=17, spaceAfter=10, wordWrap="CJK"
        )
        content = [
            Paragraph(escape(lesson["title"]), head),
            Paragraph("备课版本 V" + str(lesson["rev"]), body),
            Spacer(1, 6),
        ]
        for section, part in blocks:
            content.extend(
                [Paragraph(escape(section), head), Paragraph(escape(part).replace("\n", "<br/>"), body)]
            )
        SimpleDocTemplate(str(tmp)).build(content)
    tmp.replace(target)
    return {"format": form, "name": lesson["title"] + "." + form}


def require_job(db, user, key, lock=False):
    job = required(row(db, jobs, key, lock))
    if user["role"] != "admin" and job["owner"] != user["id"]:
        fail(403, "无权访问此任务")
    return job


def stale(job):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated"])).total_seconds() > 150


def execute(key):
    token = uid()
    with transaction() as db:
        job = row(db, jobs, key, True)
        if not job or job["state"] in TERMINAL or (job["state"] == "运行中" and not stale(job)):
            return
        state = {**job["checkpoint"], "_token": token}
        change(db, jobs, key, state="运行中", checkpoint=state, updated=now())
        user = row(db, users, job["owner"])

    def guard(db):
        j = row(db, jobs, key, True)
        if j["state"] != "运行中" or j["checkpoint"].get("_token") != token:
            raise Stopped()
        u = row(db, users, j["owner"])
        if not u["active"]:
            fail(403, "账号已停用")
        return j

    def checkpoint(phase, values):
        with transaction() as db:
            j = guard(db)
            change(db, jobs, key, phase=phase, checkpoint={**j["checkpoint"], **values}, updated=now())

    try:
        kind, payload = job["kind"], job["input"]
        output = {}
        if kind == "generate":
            generated = generate(
                user, payload, {k: v for k, v in state.items() if k != "_token"}, checkpoint
            )
        if kind == "export":
            output = render_export(key, payload)
        with transaction() as db:
            guard(db)
            if kind == "generate":
                mode = generated["mode"]
                sources = generated["sources"]
                material = Material(
                    title="定值电阻探究 · " + payload["prompt"][:36],
                    kind="交互演示",
                    chapter="九年级 · 欧姆定律",
                    point="电流与电压的关系",
                    source=(
                        mode
                        + "；"
                        + (
                            "、".join(x["title"] + " V" + str(x["number"]) for x in sources)
                            or "内置物理模型"
                        )
                    )[:400],
                    body=payload["prompt"],
                    config=generated["config"],
                )
                v = make_version(db, user, material, payload.get("resource"), status="待审核")
                for hit in sources:
                    add(
                        db,
                        citations,
                        version=v["id"],
                        source_version=hit["version"],
                        position=hit["position"],
                        excerpt=hit["body"],
                    )
                output = {
                    "version": v["id"],
                    "resource": v["resource"],
                    "config": v["config"],
                    "mode": mode,
                    "sources": sources,
                    "reason": generated.get("error", ""),
                }
            if kind == "grade":
                output = grade(db, user, payload)
            if kind == "analyze":
                output = analyze(db, user, payload)
            change(db, jobs, key, state="完成", phase="完成", result=output, updated=now())
            log(db, user["id"], "完成任务 " + kind, key, output.get("reason", ""))
    except Stopped:
        return
    except Exception as exc:
        message = (
            str(exc.detail)
            if isinstance(exc, HTTPException)
            else type(exc).__name__ + "：" + str(exc)[:250]
        )
        with transaction() as db:
            j = row(db, jobs, key, True)
            if j["state"] == "运行中" and j["checkpoint"].get("_token") == token:
                change(db, jobs, key, state="失败", error=message, updated=now())
                log(db, user["id"], "任务失败", key, message)


@celery.task(name="classroom.run")
def run(key):
    execute(key)


def dispatch(key):
    if os.getenv("TASK_MODE") == "celery":
        run.delay(key)
    else:
        pool.submit(execute, key)


@celery.task(name="classroom.recover")
def recover():
    with transaction(False) as db:
        pending = rows(db, select(jobs).where(jobs.c.state.in_(["排队中", "运行中"])))
    for j in pending:
        if j["state"] == "排队中" or stale(j):
            dispatch(j["id"])


@router.post("/{kind}")
def enqueue(kind: str, data: dict, user=Depends(current)):
    with transaction() as db:
        if kind == "generate":
            roles(user, STAFF)
            entry = Generate(**data)
            payload = entry.model_dump()
            payload["settings"] = row(db, settings, "generation")["value"]
            if entry.parent:
                parent = require_job(db, user, entry.parent)
                if parent["state"] != "完成" or parent["kind"] != "generate":
                    fail(409, "上一轮生成尚未完成")
                payload["history"] = (
                    parent["input"].get("history", [])
                    + [{"prompt": parent["input"]["prompt"], "config": parent["result"]["config"]}]
                )[-6:]
                payload["resource"] = parent["result"]["resource"]
        elif kind == "export":
            req = Export(**data)
            if req.format not in {"pdf", "docx"}:
                fail(422, "未知导出格式")
            ls = lesson_access(db, user, req.lesson)
            payload = {**req.model_dump(), "snapshot": ls, "citations": []}
            for ref in ls["refs"]:
                v = row(db, versions, ref)
                payload["citations"].append(
                    v["title"] + " · V" + str(v["number"]) + " · " + v["source"]
                )
        elif kind == "grade":
            roles(user, {"student"})
            payload = Answer(**data).model_dump()
            paper = required(row(db, papers, payload["paper"]))
            pub_access(db, user, paper["pub"], True)
        elif kind == "analyze":
            roles(user, STAFF | {"admin"})
            payload = Analysis(**data).model_dump()
            pub_access(db, user, payload["pub"])
        else:
            fail(404, "未知任务类型")
        job = add(
            db,
            jobs,
            owner=user["id"],
            kind=kind,
            state="排队中",
            phase="已登记",
            input=payload,
            checkpoint={},
            result={},
            error="",
            created=now(),
            updated=now(),
        )
    dispatch(job["id"])
    return {"id": job["id"]}


def view(j):
    preview = j["checkpoint"].get("config")
    return {
        **{k: j[k] for k in ("id", "kind", "owner", "state", "phase", "result", "error", "updated")},
        "preview": preview,
        "prompt": j["input"].get("prompt", ""),
    }


@router.get("")
def my_jobs(user=Depends(current)):
    with transaction(False) as db:
        stmt = select(jobs)
        if user["role"] != "admin":
            stmt = stmt.where(jobs.c.owner == user["id"])
        return [view(j) for j in rows(db, stmt.order_by(jobs.c.created.desc()).limit(80))]


@router.get("/{key}")
def job_state(key: str, user=Depends(current)):
    with transaction(False) as db:
        return view(require_job(db, user, key))


@router.get("/{key}/stream")
async def stream(key: str, user=Depends(current)):
    job_state(key, user)

    async def events():
        last = None
        while True:
            state = await asyncio.to_thread(job_state, key, user)
            if state != last:
                yield "data: " + json.dumps(state, ensure_ascii=False) + "\n\n"
                last = state
            if state["state"] in TERMINAL:
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/{key}/cancel")
def cancel(key: str, user=Depends(current)):
    with transaction() as db:
        j = require_job(db, user, key, True)
        if j["state"] in TERMINAL:
            fail(409, "任务已结束")
        change(db, jobs, key, state="已取消", updated=now())
        log(db, user["id"], "取消任务", key)
        return {"ok": True}


@router.post("/{key}/resume")
def resume(key: str, user=Depends(current)):
    with transaction() as db:
        j = require_job(db, user, key, True)
        if j["state"] not in ("失败", "已取消") and not (j["state"] == "运行中" and stale(j)):
            fail(409, "此任务不能恢复")
        change(db, jobs, key, state="排队中", phase="恢复检查点", error="", updated=now())
        log(db, user["id"], "恢复任务", key)
    dispatch(key)
    return {"id": key}


@router.get("/{key}/file")
def exported(key: str, user=Depends(current)):
    with transaction(False) as db:
        j = require_job(db, user, key)
        if j["kind"] != "export" or j["state"] != "完成":
            fail(409, "导出尚未就绪")
        return FileResponse(
            ROOT / "exports" / (key + "." + j["result"]["format"]), filename=j["result"]["name"]
        )
