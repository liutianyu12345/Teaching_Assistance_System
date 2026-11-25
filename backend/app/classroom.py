import asyncio
import json
import random
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from .access import STAFF, current, fail, identity, pub_access, required, roles
from .db import (
    ROOT,
    activities,
    add,
    change,
    discussions,
    lessons,
    log,
    now,
    observations,
    pubs,
    reports,
    responses,
    row,
    rows,
    transaction,
    update,
    users,
    uses,
)
from .physics import Circuit
from .live import view as cached_view

router = APIRouter(prefix="/api")
KINDS = {"投票", "选择题", "判断题", "抢答", "分组讨论", "随机点名"}


@router.get("/classrooms")
def classrooms(user=Depends(current)):
    roles(user, STAFF | {"admin", "student"})
    with transaction(False) as db:
        stmt = select(pubs).join(lessons, lessons.c.id == pubs.c.lesson)
        if user["role"] != "admin":
            stmt = stmt.where(
                pubs.c.class_id.in_(user["classes"]), lessons.c.group_id == user["group_id"]
            )
        return rows(db, stmt.order_by(pubs.c.created.desc()))


@router.post("/classrooms/{key}/withdraw")
def withdraw(key: str, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        p = pub_access(db, user, key, True, True)
        if p["teacher"] != user["id"]:
            fail(403, "仅发布教师可撤回课堂")
        change(db, pubs, key, active=False)
        db.info.setdefault("classroom_changes", set()).add(key)
        db.execute(update(activities).where(activities.c.pub == key).values(state="已结束"))
        log(db, user["id"], "撤回课堂", key)
        return {"ok": True}


@router.post("/classrooms/{key}/materials/{version}/open")
def open_material(key: str, version: str, user=Depends(current)):
    with transaction() as db:
        p = pub_access(db, user, key, True)
        v = next((v for v in p["snapshot"]["resources"] if v["id"] == version), None) or fail(
            404, "课堂未引用此资源"
        )
        if user["role"] == "student":
            add(db, uses, pub=key, version=version, student=user["id"], created=now())
        return {"body": v["body"], "file": bool(v["attachment"])}


@router.get("/classrooms/{key}/materials/{version}/file")
def download(key: str, version: str, user=Depends(current)):
    with transaction(False) as db:
        p = pub_access(db, user, key, True)
        v = next(
            (v for v in p["snapshot"]["resources"] if v["id"] == version and v["attachment"]), None
        ) or fail(404, "课堂无此附件")
        return FileResponse(ROOT / "uploads" / v["attachment"], filename=v["filename"])


class Trial(BaseModel):
    voltage: float = Field(allow_inf_nan=False)
    note: str = Field(default="", max_length=1000)
    submission: str = Field(min_length=1, max_length=100)


@router.post("/classrooms/{key}/observations")
def observe(key: str, data: Trial, user=Depends(current)):
    roles(user, {"student"})
    with transaction() as db:
        p = pub_access(db, user, key, True, True)
        old = (
            db.execute(
                select(observations).where(
                    observations.c.pub == key,
                    observations.c.student == user["id"],
                    observations.c.submission == data.submission,
                )
            )
            .mappings()
            .first()
        )
        if old:
            return old
        try:
            amps = Circuit(**p["snapshot"]["config"]).reading(data.voltage)
        except ValueError as e:
            fail(422, str(e))
        return add(
            db,
            observations,
            pub=key,
            student=user["id"],
            current=amps,
            **data.model_dump(),
            created=now()
        )


class Report(BaseModel):
    body: str = Field(min_length=1, max_length=6000)


@router.post("/classrooms/{key}/report")
def report(key: str, data: Report, user=Depends(current)):
    roles(user, {"student"})
    with transaction() as db:
        pub_access(db, user, key, True, True)
        existing = db.scalar(
            select(reports.c.id).where(reports.c.pub == key, reports.c.student == user["id"])
        )
        if existing:
            change(db, reports, existing, body=data.body, created=now())
        else:
            add(db, reports, pub=key, student=user["id"], body=data.body, created=now())
        return {"ok": True}


@router.get("/classrooms/{key}/records")
def records(key: str, user=Depends(current)):
    with transaction(False) as db:
        pub_access(db, user, key)
        result = {}
        for t in (observations, reports):
            stmt = select(t, users.c.name).join(users, users.c.id == t.c.student).where(t.c.pub == key)
            if user["role"] == "student":
                stmt = stmt.where(t.c.student == user["id"])
            result[t.name] = rows(db, stmt.order_by(t.c.created))
        return result


class ActivityInput(BaseModel):
    kind: str
    prompt: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(default_factory=list, max_length=12)


def activity_state(db, key, user):
    acts = rows(
        db, select(activities).where(activities.c.pub == key).order_by(activities.c.created.desc())
    )
    for a in acts:
        replies = rows(
            db,
            select(responses, users.c.name)
            .join(users, users.c.id == responses.c.student)
            .where(responses.c.activity == a["id"])
            .order_by(responses.c.created),
        )
        a["count"] = len(replies)
        a["counts"] = (
            dict(Counter(r["answer"] for r in replies))
            if a["kind"] != "分组讨论" or user["role"] != "student"
            else {}
        )
        a["mine"] = next((r["answer"] for r in replies if r["student"] == user["id"]), None)
        if user["role"] != "student":
            a["replies"] = replies
        if a["kind"] == "分组讨论":
            teams = json.loads(a["options"][0])
            mine = teams.get(user["id"])
            a["team"] = mine
            a["options"] = []
            messages = (
                select(discussions, users.c.name)
                .join(users, users.c.id == discussions.c.student)
                .where(discussions.c.activity == a["id"])
            )
            if user["role"] == "student":
                messages = messages.where(discussions.c.team == mine)
            a["messages"] = rows(db, messages.order_by(discussions.c.created))
            a["count"] = len({m["student"] for m in a["messages"]})
    return acts


@router.get("/classrooms/{key}/activities")
def activity_list(key: str, user=Depends(current)):
    with transaction(False) as db:
        pub_access(db, user, key)
        return activity_state(db, key, user)


@router.post("/classrooms/{key}/activities")
def activity(key: str, data: ActivityInput, user=Depends(current)):
    roles(user, STAFF)
    if data.kind not in KINDS:
        fail(422, "未知活动类型")
    with transaction() as db:
        p = pub_access(db, user, key, True, True)
        opts = data.options
        if data.kind == "判断题":
            opts = ["正确", "错误"]
        if data.kind in ("选择题", "投票") and len(set(opts)) < 2:
            fail(422, "请提供至少两个不同选项")
        if data.kind == "随机点名":
            students = [
                u["name"]
                for u in rows(
                    db,
                    select(users).where(
                        users.c.role == "student",
                        users.c.active.is_(True),
                        users.c.group_id == user["group_id"],
                    ),
                )
                if p["class_id"] in u["classes"]
            ]
            if not students:
                fail(409, "该班暂无学生")
            opts = [random.SystemRandom().choice(students)]
        if data.kind == "分组讨论":
            roster = [
                u["id"]
                for u in rows(
                    db,
                    select(users)
                    .where(
                        users.c.role == "student",
                        users.c.active.is_(True),
                        users.c.group_id == user["group_id"],
                    )
                    .order_by(users.c.id),
                )
                if p["class_id"] in u["classes"]
            ]
            opts = [
                json.dumps(
                    {student: "第 " + str(i // 4 + 1) + " 组" for i, student in enumerate(roster)},
                    ensure_ascii=False,
                )
            ]
        db.info.setdefault("classroom_changes", set()).add(key)
        return add(
            db,
            activities,
            pub=key,
            kind=data.kind,
            prompt=data.prompt,
            options=opts,
            state="已结束" if data.kind == "随机点名" else "开放",
            created=now(),
        )


@router.post("/activities/{key}/state/{state}")
def advance(key: str, state: str, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        a = required(row(db, activities, key))
        pub_access(db, user, a["pub"], True, True)
        a = row(db, activities, key, True)
        if (a["state"], state) not in (("开放", "截止"), ("开放", "已结束"), ("截止", "已结束")):
            fail(409, "活动状态已变更")
        change(db, activities, key, state=state)
        db.info.setdefault("classroom_changes", set()).add(a["pub"])
        return {"state": state}


@router.post("/activities/{key}/answer")
def answer(key: str, data: Report, user=Depends(current)):
    roles(user, {"student"})
    with transaction() as db:
        a = required(row(db, activities, key))
        pub_access(db, user, a["pub"], True, True)
        a = row(db, activities, key, True)
        if a["kind"] == "分组讨论":
            fail(422, "请使用小组发言入口")
        old = (
            db.execute(
                select(responses).where(responses.c.activity == key, responses.c.student == user["id"])
            )
            .mappings()
            .first()
        )
        if old:
            return old
        if a["state"] != "开放":
            fail(409, "活动已截止")
        if a["kind"] == "抢答" and db.scalar(
            select(responses.c.id).where(responses.c.activity == key).limit(1)
        ):
            fail(409, "已有同学抢答成功")
        if a["kind"] in ("投票", "判断题", "选择题") and data.body not in a["options"]:
            fail(422, "选项无效")
        db.info.setdefault("classroom_changes", set()).add(a["pub"])
        return add(db, responses, activity=key, student=user["id"], answer=data.body, created=now())


class Message(Report):
    submission: str = Field(min_length=1, max_length=100)


@router.post("/activities/{key}/discuss")
def discuss(key: str, data: Message, user=Depends(current)):
    roles(user, {"student"})
    with transaction() as db:
        a = required(row(db, activities, key))
        pub_access(db, user, a["pub"], True, True)
        a = row(db, activities, key, True)
        if a["kind"] != "分组讨论":
            fail(422, "活动类型错误")
        team = json.loads(a["options"][0]).get(user["id"]) or fail(403, "未分配到该活动小组")
        old = (
            db.execute(
                select(discussions).where(
                    discussions.c.activity == key,
                    discussions.c.student == user["id"],
                    discussions.c.submission == data.submission,
                )
            )
            .mappings()
            .first()
        )
        if old:
            return old
        if a["state"] != "开放":
            fail(409, "活动已截止")
        db.info.setdefault("classroom_changes", set()).add(a["pub"])
        return add(
            db,
            discussions,
            activity=key,
            student=user["id"],
            team=team,
            **data.model_dump(),
            created=now()
        )


@router.websocket("/ws/classrooms/{key}")
async def live(ws: WebSocket, key: str):
    from urllib.parse import urlsplit

    origin = ws.headers.get("origin")
    if origin and urlsplit(origin).netloc != ws.headers.get("host"):
        return await ws.close(code=1008)
    token = ws.cookies.get("session")
    if not identity(token):
        return await ws.close(code=1008)
    await ws.accept()
    previous = None
    try:
        while True:
            user = await asyncio.to_thread(identity, token)
            if not user:
                return await ws.close(code=1008)

            def snapshot():
                with transaction(False) as db:
                    p = pub_access(db, user, key)
                    return {
                        "active": p["active"],
                        "activities": cached_view(
                            key, user["id"], lambda: activity_state(db, key, user)
                        ),
                    }

            data = await asyncio.to_thread(snapshot)
            if data != previous:
                await ws.send_json(data)
                previous = data
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.75)
            except asyncio.TimeoutError:
                pass
    except HTTPException:
        await ws.close(code=1008)
    except WebSocketDisconnect:
        pass
