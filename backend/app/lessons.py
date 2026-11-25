from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from .access import STAFF, current, fail, group, lesson_access, required, roles
from .db import (
    add,
    change,
    comments,
    history,
    lessons,
    log,
    now,
    pubs,
    resources,
    row,
    rows,
    transaction,
    users,
    versions,
)

router = APIRouter(prefix="/api")
SECTIONS = {
    "目标": "观察定值电阻两端电压变化时的电流，归纳两者的关系。",
    "重难点": "保持电阻不变，区分自变量、因变量和控制变量。",
    "实验": "依次调节电压并记录至少三组数据，在坐标系中比较数据点。",
    "讲解": "在电阻固定时，电压与电流成正比。",
    "提问": "电压增大一倍，电流会发生什么变化？",
    "练习": "结合图线斜率，解释同一电阻的电压、电流关系。",
    "作业": "写出实验结论，并说明成立条件。",
}


def remember(db, lesson, user):
    add(
        db,
        history,
        lesson=lesson["id"],
        rev=lesson["rev"],
        data=lesson,
        actor=user["id"],
        created=now(),
    )


def update_lesson(db, lesson, user, **updates):
    updates["rev"] = lesson["rev"] + 1
    change(db, lessons, lesson["id"], **updates)
    new = {**lesson, **updates}
    remember(db, new, user)
    return new


def approved(db, user, keys):
    result = []
    for key in dict.fromkeys(keys):
        v = required(row(db, versions, key, True))
        group(user, row(db, resources, v["resource"])["group_id"])
        if v["status"] != "已发布":
            fail(409, "引用的资源需要处于审核通过且已发布状态")
        result.append(v)
    return result


class LessonInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    refs: list[str] = Field(default_factory=list, max_length=100)
    collabs: list[str] = Field(default_factory=list, max_length=50)
    template: bool = True


def create_lesson(db, user, data):
    approved(db, user, data.refs)
    verify_collabs(db, user, data.collabs)
    lesson = add(
        db,
        lessons,
        owner=user["id"],
        group_id=user["group_id"],
        title=data.title,
        state="草稿",
        rev=1,
        sections={k: {"text": v if data.template else "", "rev": 1} for k, v in SECTIONS.items()},
        refs=data.refs,
        collabs=data.collabs,
    )
    remember(db, lesson, user)
    return lesson


def verify_collabs(db, user, ids):
    for key in ids:
        other = required(row(db, users, key))
        if other["group_id"] != user["group_id"] or other["role"] not in STAFF:
            fail(422, "协作者须为同组教师")


@router.post("/lessons")
def create(data: LessonInput, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        return create_lesson(db, user, data)


@router.get("/lessons")
def listing(user=Depends(current)):
    roles(user, STAFF | {"admin"})
    with transaction(False) as db:
        stmt = select(lessons)
        if user["role"] != "admin":
            stmt = stmt.where(lessons.c.group_id == user["group_id"])
        return rows(db, stmt.order_by(lessons.c.title))


class SectionEdit(BaseModel):
    section: str
    text: str = Field(max_length=12000)
    rev: int


@router.put("/lessons/{key}/section")
def edit(key: str, data: SectionEdit, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True, True)
        sec = ls["sections"].get(data.section) or fail(422, "未知备课章节")
        if sec["rev"] != data.rev:
            fail(409, {"message": "章节已变更，请比较内容后重新提交", "current": sec})
        sections = {**ls["sections"], data.section: {"text": data.text, "rev": sec["rev"] + 1}}
        return update_lesson(db, ls, user, sections=sections, state="协作中")


class LessonMeta(BaseModel):
    rev: int
    refs: list[str]
    collabs: list[str]


@router.put("/lessons/{key}/links")
def links(key: str, data: LessonMeta, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True, True)
        if ls["owner"] != user["id"]:
            fail(403, "仅负责人可指定资源和协作者")
        if ls["rev"] != data.rev:
            fail(409, "备课包已更新，请刷新")
        approved(db, user, data.refs)
        verify_collabs(db, user, data.collabs)
        return update_lesson(db, ls, user, refs=data.refs, collabs=data.collabs, state="草稿")


@router.get("/lessons/{key}/history")
def records(key: str, user=Depends(current)):
    with transaction(False) as db:
        lesson_access(db, user, key)
        return rows(db, select(history).where(history.c.lesson == key).order_by(history.c.rev.desc()))


class Revision(BaseModel):
    rev: int


@router.post("/lessons/{key}/restore/{rev}")
def restore(key: str, rev: int, data: Revision, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True, True)
        if ls["rev"] != data.rev:
            fail(409, "备课包已更新")
        item = required(
            db.execute(select(history).where(history.c.lesson == key, history.c.rev == rev))
            .mappings()
            .first()
        )["data"]
        sections = {
            k: {"text": v["text"], "rev": ls["sections"][k]["rev"] + 1}
            for k, v in item["sections"].items()
        }
        log(db, user["id"], "恢复备课版本", key, str(rev))
        return update_lesson(db, ls, user, sections=sections, refs=item["refs"], state="草稿")


class Note(BaseModel):
    section: str
    body: str = Field(min_length=1, max_length=2000)


@router.get("/lessons/{key}/comments")
def notes(key: str, user=Depends(current)):
    with transaction(False) as db:
        lesson_access(db, user, key)
        return rows(
            db,
            select(comments, users.c.name)
            .join(users, users.c.id == comments.c.actor)
            .where(comments.c.lesson == key)
            .order_by(comments.c.created),
        )


@router.post("/lessons/{key}/comments")
def add_note(key: str, data: Note, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True)
        if data.section not in ls["sections"]:
            fail(422, "未知章节")
        return add(db, comments, lesson=key, actor=user["id"], **data.model_dump(), created=now())


@router.post("/lessons/{key}/finalize")
def finalize(key: str, data: Revision, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True, True)
        if ls["owner"] != user["id"]:
            fail(403, "仅负责人可定稿")
        if ls["rev"] != data.rev or ls["state"] not in ("草稿", "协作中"):
            fail(409, "请核对当前备课版本与状态")
        approved(db, user, ls["refs"])
        return update_lesson(db, ls, user, state="定稿")


class Publish(Revision):
    class_id: str


def publish(db, user, ls, class_id):
    if class_id not in user["classes"] or user["id"] != ls["owner"]:
        fail(403, "仅负责人可向任教班级发布")
    if ls["state"] not in ("定稿", "已发布"):
        fail(409, "请先定稿")
    materials = approved(db, user, ls["refs"])
    experiments = [v for v in materials if v["config"]]
    if len(experiments) != 1:
        fail(422, "本课例须引用一个已审核的定值电阻实验")
    data = {
        "title": ls["title"],
        "lesson_rev": ls["rev"],
        "sections": ls["sections"],
        "resources": materials,
        "config": experiments[0]["config"],
    }
    p = add(
        db,
        pubs,
        teacher=user["id"],
        lesson=ls["id"],
        class_id=class_id,
        snapshot=data,
        active=True,
        created=now(),
    )
    log(db, user["id"], "发布课堂快照", p["id"], class_id)
    if ls["state"] != "已发布":
        update_lesson(db, ls, user, state="已发布")
    return p


@router.post("/lessons/{key}/publish")
def release(key: str, data: Publish, user=Depends(current)):
    with transaction() as db:
        ls = lesson_access(db, user, key, True, True)
        if ls["rev"] != data.rev:
            fail(409, "备课版本已更新")
        return publish(db, user, ls, data.class_id)
