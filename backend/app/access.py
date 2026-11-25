import hashlib
import os
import secrets
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from .db import (
    add,
    audit,
    change,
    lessons,
    log,
    password,
    pubs,
    row,
    rows,
    sessions,
    settings,
    transaction,
    users,
)

router = APIRouter(prefix="/api")
STAFF = {"teacher", "lead"}
ROLES = STAFF | {"student", "reviewer", "admin"}
DEMO = os.getenv("DEMO_MODE", "1") == "1"


def fail(code, message):
    raise HTTPException(code, message)


def required(item):
    if item is None:
        fail(404, "记录不存在")
    return item


def identity(token):
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with transaction(False) as db:
        session = row(db, sessions, digest)
        if session and session["expires"] > time.time():
            user = row(db, users, session["user_id"])
            if user and user["active"]:
                return user


def current(session: str | None = Cookie(None)):
    return identity(session) or fail(401, "请登录教学工作台")


def roles(user, allowed):
    if user["role"] not in allowed:
        fail(403, "当前角色无此操作权限")


def group(user, group_id):
    if user["role"] != "admin" and user["group_id"] != group_id:
        fail(403, "超出教研组范围")


def lesson_access(db, user, key, edit=False, lock=False):
    lesson = required(row(db, lessons, key, lock))
    roles(user, STAFF | {"admin"})
    group(user, lesson["group_id"])
    if edit and user["id"] != lesson["owner"] and user["id"] not in lesson["collabs"]:
        fail(403, "仅备课负责人和指定协作者可编辑")
    return lesson


def pub_access(db, user, key, write=False, lock=False):
    roles(user, STAFF | {"admin", "student"})
    pub = required(row(db, pubs, key, lock))
    if user["role"] != "admin" and pub["class_id"] not in user["classes"]:
        fail(403, "超出所属班级")
    if user["role"] != "admin":
        group(user, required(row(db, lessons, pub["lesson"]))["group_id"])
    if write and not pub["active"]:
        fail(409, "课堂已撤回")
    return pub


def public_user(user):
    return {k: user[k] for k in ("id", "username", "name", "role", "group_id", "classes", "active")}


class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=160)


@router.post("/login")
def login(data: Login, response: Response):
    with transaction() as db:
        user = db.execute(select(users).where(users.c.username == data.username)).mappings().first()
        if (
            not user
            or not user["active"]
            or not secrets.compare_digest(
                password(data.password, user["password"].split(":")[0]), user["password"]
            )
        ):
            fail(401, "账号或密码错误")
        token = secrets.token_urlsafe(32)
        add(
            db,
            sessions,
            id=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user["id"],
            expires=time.time() + 43200,
        )
        response.set_cookie(
            "session",
            token,
            httponly=True,
            samesite="strict",
            secure=os.getenv("COOKIE_SECURE") == "1",
            max_age=43200,
        )
        return public_user(user)


@router.post("/logout")
def logout(response: Response, session: str | None = Cookie(None)):
    with transaction() as db:
        if session:
            db.execute(
                delete(sessions).where(sessions.c.id == hashlib.sha256(session.encode()).hexdigest())
            )
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current)):
    return public_user(user)


@router.get("/demo")
def demo():
    return {"enabled": DEMO}


@router.get("/people")
def people(user=Depends(current)):
    roles(user, STAFF | {"admin"})
    with transaction(False) as db:
        stmt = select(users).order_by(users.c.name)
        if user["role"] != "admin":
            stmt = stmt.where(users.c.group_id == user["group_id"], users.c.role.in_(STAFF))
        return list(map(public_user, rows(db, stmt)))


class Account(Login):
    name: str = Field(min_length=1, max_length=80)
    role: str
    group_id: str = Field(min_length=1, max_length=80)
    classes: list[str]


@router.post("/people")
def create_account(data: Account, user=Depends(current)):
    roles(user, {"admin"})
    if data.role not in ROLES or len(data.password) < 8:
        fail(422, "请选择有效角色，密码至少八位")
    with transaction() as db:
        if db.scalar(select(users.c.id).where(users.c.username == data.username)):
            fail(409, "账号已存在")
        item = add(
            db,
            users,
            **data.model_dump(exclude={"password"}),
            password=password(data.password),
            active=True
        )
        log(db, user["id"], "创建账号", item["id"])
        return public_user(item)


@router.post("/people/{key}/toggle")
def toggle(key: str, user=Depends(current)):
    roles(user, {"admin"})
    if key == user["id"]:
        fail(409, "当前登录账号须保持启用")
    with transaction() as db:
        item = required(row(db, users, key, True))
        change(db, users, key, active=not item["active"])
        db.execute(delete(sessions).where(sessions.c.user_id == key))
        log(db, user["id"], "变更账号状态", key)
        return {"ok": True}


@router.get("/audit")
def logs(user=Depends(current)):
    roles(user, {"admin", "lead", "reviewer"})
    with transaction(False) as db:
        stmt = select(audit, users.c.name).join(users, users.c.id == audit.c.actor)
        if user["role"] != "admin":
            stmt = stmt.where(users.c.group_id == user["group_id"])
        return rows(db, stmt.order_by(audit.c.created.desc()).limit(300))


class Config(BaseModel):
    repair_limit: int = Field(ge=0, le=3)
    timeout: int = Field(ge=2, le=60)


@router.get("/settings")
def config(user=Depends(current)):
    roles(user, {"admin"})
    with transaction(False) as db:
        return row(db, settings, "generation")["value"]


@router.put("/settings")
def set_config(data: Config, user=Depends(current)):
    roles(user, {"admin"})
    with transaction() as db:
        change(db, settings, "generation", value=data.model_dump())
        log(db, user["id"], "修改生成配置", "generation")
        return data
