import json
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from .db import (
    PG,
    ROOT,
    add,
    change,
    chunks,
    citations,
    now,
    resources,
    row,
    rows,
    transaction,
    uid,
    versions,
)
from .access import STAFF, current, fail, group, log, required, roles
from .physics import Circuit, embedding

router = APIRouter(prefix="/api")


class Material(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    kind: str = Field(min_length=1, max_length=40)
    chapter: str = Field(min_length=1, max_length=100)
    point: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=400)
    body: str = Field(min_length=1, max_length=32000)
    config: Circuit | None = None


def make_version(db, user, data, resource=None, attachment="", filename="", status="草稿"):
    if resource:
        parent = required(row(db, resources, resource, True))
        group(user, parent["group_id"])
        if parent["owner"] != user["id"]:
            fail(403, "仅资源作者可创建修订")
        number = (
            db.scalar(
                select(versions.c.number)
                .where(versions.c.resource == resource)
                .order_by(versions.c.number.desc())
                .limit(1)
            )
            + 1
        )
    else:
        resource = add(db, resources, owner=user["id"], group_id=user["group_id"])["id"]
        number = 1
    version = add(
        db,
        versions,
        resource=resource,
        number=number,
        **data.model_dump(),
        attachment=attachment,
        filename=filename,
        status=status,
        feedback="",
        created=now(),
    )
    body = data.body
    for pos in range(0, len(body), 400):
        part = body[pos : pos + 400]
        chunk = add(db, chunks, version=version["id"], position=pos, body=part)
        if PG:
            db.execute(
                text("UPDATE knowledge_chunks SET embedding=CAST(:v AS vector) WHERE id=:id"),
                {"v": json.dumps(embedding(part)), "id": chunk["id"]},
            )
    log(db, user["id"], "创建资源版本", version["id"])
    return version


def retrieve(db, user, q):
    stmt = (
        select(
            chunks.c.body,
            chunks.c.position,
            chunks.c.version,
            versions.c.title,
            versions.c.number,
            versions.c.source,
        )
        .select_from(
            chunks.join(versions, chunks.c.version == versions.c.id).join(
                resources, versions.c.resource == resources.c.id
            )
        )
        .where(resources.c.group_id == user["group_id"], versions.c.status == "已发布")
    )
    vec = embedding(q)
    if PG:
        return rows(
            db,
            stmt.order_by(text("knowledge_chunks.embedding <=> CAST(:v AS vector)"))
            .params(v=json.dumps(vec))
            .limit(5),
        )
    hits = rows(db, stmt)
    return sorted(
        hits, key=lambda h: sum(a * b for a, b in zip(vec, embedding(h["body"]))), reverse=True
    )[:5]


@router.get("/knowledge")
def knowledge(q: str, user=Depends(current)):
    roles(user, STAFF | {"reviewer", "admin"})
    with transaction(False) as db:
        return retrieve(db, user, q)


@router.get("/resources")
def listing(
    q: str = "",
    chapter: str = "",
    point: str = "",
    kind: str = "",
    status: str = "",
    user=Depends(current),
):
    roles(user, STAFF | {"reviewer", "admin"})
    with transaction(False) as db:
        stmt = select(versions, resources.c.owner).join(
            resources, resources.c.id == versions.c.resource
        )
        if user["role"] != "admin":
            stmt = stmt.where(resources.c.group_id == user["group_id"])
        for column, value in [
            (versions.c.chapter, chapter),
            (versions.c.point, point),
            (versions.c.kind, kind),
            (versions.c.status, status),
        ]:
            if value:
                stmt = stmt.where(column == value)
        if q:
            stmt = stmt.where(versions.c.title.contains(q) | versions.c.body.contains(q))
        return rows(db, stmt.order_by(versions.c.created.desc()))


@router.post("/resources")
def create(data: Material, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        return make_version(db, user, data)


@router.post("/resources/{key}/revise")
def revise(key: str, data: Material, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        old = required(row(db, versions, key))
        new = make_version(db, user, data, old["resource"], old["attachment"], old["filename"])
        for cite in rows(db, select(citations).where(citations.c.version == key)):
            add(
                db,
                citations,
                version=new["id"],
                source_version=cite["source_version"],
                position=cite["position"],
                excerpt=cite["excerpt"],
            )
        return new


@router.get("/resources/{key}/sources")
def version_sources(key: str, user=Depends(current)):
    roles(user, STAFF | {"reviewer", "admin"})
    with transaction(False) as db:
        v = required(row(db, versions, key))
        group(user, row(db, resources, v["resource"])["group_id"])
        stmt = (
            select(citations, versions.c.title, versions.c.number, versions.c.source)
            .join(versions, versions.c.id == citations.c.source_version)
            .where(citations.c.version == key)
        )
        return rows(db, stmt.order_by(versions.c.title, citations.c.position))


@router.post("/resources/{key}/file")
def upload(key: str, file: UploadFile = File(...), user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        v = required(row(db, versions, key, True))
        if row(db, resources, v["resource"])["owner"] != user["id"]:
            fail(403, "仅作者可上传")
        if v["status"] != "草稿":
            fail(409, "只能向草稿上传文件")
        path = ROOT / "uploads" / uid()
        path.parent.mkdir(exist_ok=True)
        try:
            with path.open("wb") as f:
                while block := file.file.read(1024 * 1024):
                    if f.tell() + len(block) > 32 * 1024 * 1024:
                        fail(413, "附件上限为 32 MB")
                    f.write(block)
            change(db, versions, key, attachment=path.name, filename=Path(file.filename or "附件").name)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {"ok": True}


@router.get("/resources/{key}/file")
def attachment(key: str, user=Depends(current)):
    roles(user, STAFF | {"reviewer", "admin"})
    with transaction(False) as db:
        v = required(row(db, versions, key))
        group(user, row(db, resources, v["resource"])["group_id"])
        if not v["attachment"]:
            fail(404, "无附件")
        return FileResponse(ROOT / "uploads" / v["attachment"], filename=v["filename"])


class Review(BaseModel):
    action: str
    feedback: str = Field(default="", max_length=1000)


@router.post("/resources/{key}/review")
def review(key: str, data: Review, user=Depends(current)):
    roles(user, STAFF | {"admin", "reviewer"})
    transitions = {
        ("草稿", "提交"): "待审核",
        ("待审核", "通过"): "已发布",
        ("待审核", "退回"): "已退回",
        ("已发布", "撤回"): "已撤回",
        ("已撤回", "归档"): "已归档",
    }
    with transaction() as db:
        v = required(row(db, versions, key, True))
        r = row(db, resources, v["resource"])
        group(user, r["group_id"])
        if data.action == "提交" and user["id"] != r["owner"]:
            fail(403, "仅作者可提交")
        if (
            data.action in ("撤回", "归档")
            and user["id"] != r["owner"]
            and user["role"] not in {"lead", "reviewer", "admin"}
        ):
            fail(403, "无权管理该版本")
        if data.action == "退回" and not data.feedback.strip():
            fail(422, "请填写退回意见")
        state = transitions.get((v["status"], data.action)) or fail(409, "不允许当前状态转换")
        if state == "已发布" and v["config"]:
            Circuit.model_validate(v["config"])
        change(db, versions, key, status=state, feedback=data.feedback)
        log(db, user["id"], data.action + "资源", key, data.feedback)
        return {"status": state}
