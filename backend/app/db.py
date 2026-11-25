"""Relational schema and first installation migration, shared by API and worker."""

import hashlib
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
    text,
    update,
)

ROOT = Path(os.getenv("DATA_DIR", "data")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
URL = os.getenv("DATABASE_URL", "sqlite:///" + (ROOT / "classroom.db").as_posix())
PG = URL.startswith("postgresql")
engine = create_engine(
    URL,
    pool_pre_ping=True,
    **({} if PG else {"connect_args": {"check_same_thread": False, "timeout": 30}}),
)
if not PG:

    @event.listens_for(engine, "connect")
    def sqlite_settings(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")


meta = MetaData()


def col(name, typ=String, **kw):
    return Column(name, typ, nullable=False, **kw)


def fk(name, target):
    return Column(name, String, ForeignKey(target + ".id"), nullable=False)


def table(name, *fields):
    return Table(name, meta, col("id", String, primary_key=True), *fields)


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


users = table(
    "users",
    col("username", unique=True),
    col("name"),
    col("role"),
    col("group_id"),
    col("classes", JSON),
    col("password"),
    col("active", Boolean),
)
sessions = table("sessions", fk("user_id", "users"), col("expires", Float))
resources = table("resources", fk("owner", "users"), col("group_id"))
versions = table(
    "resource_versions",
    fk("resource", "resources"),
    col("number", Integer),
    col("title"),
    col("kind"),
    col("chapter"),
    col("point"),
    col("source"),
    col("body", Text),
    col("status"),
    col("config", JSON),
    col("attachment"),
    col("filename"),
    col("feedback", Text),
    col("created"),
    UniqueConstraint("resource", "number"),
)
chunks = table(
    "knowledge_chunks", fk("version", "resource_versions"), col("position", Integer), col("body", Text)
)
citations = table(
    "resource_citations",
    fk("version", "resource_versions"),
    fk("source_version", "resource_versions"),
    col("position", Integer),
    col("excerpt", Text),
)
lessons = table(
    "lessons",
    fk("owner", "users"),
    col("group_id"),
    col("title"),
    col("state"),
    col("rev", Integer),
    col("sections", JSON),
    col("refs", JSON),
    col("collabs", JSON),
)
history = table(
    "lesson_history",
    fk("lesson", "lessons"),
    col("rev", Integer),
    col("data", JSON),
    fk("actor", "users"),
    col("created"),
    UniqueConstraint("lesson", "rev"),
)
comments = table(
    "comments",
    fk("lesson", "lessons"),
    fk("actor", "users"),
    col("section"),
    col("body", Text),
    col("created"),
)
pubs = table(
    "publications",
    fk("lesson", "lessons"),
    fk("teacher", "users"),
    col("class_id"),
    col("snapshot", JSON),
    col("active", Boolean),
    col("created"),
)
activities = table(
    "activities",
    fk("pub", "publications"),
    col("kind"),
    col("prompt"),
    col("options", JSON),
    col("state"),
    col("created"),
)
responses = table(
    "responses",
    fk("activity", "activities"),
    fk("student", "users"),
    col("answer"),
    col("created"),
    UniqueConstraint("activity", "student"),
)
discussions = table(
    "discussion_messages",
    fk("activity", "activities"),
    fk("student", "users"),
    col("team"),
    col("body", Text),
    col("submission"),
    col("created"),
    UniqueConstraint("activity", "student", "submission"),
)
observations = table(
    "observations",
    fk("pub", "publications"),
    fk("student", "users"),
    col("voltage", Float),
    col("current", Float),
    col("note", Text),
    col("submission"),
    col("created"),
    UniqueConstraint("pub", "student", "submission"),
)
reports = table(
    "reports",
    fk("pub", "publications"),
    fk("student", "users"),
    col("body", Text),
    col("created"),
    UniqueConstraint("pub", "student"),
)
questions = table(
    "questions",
    col("group_id"),
    col("point"),
    col("difficulty"),
    col("kind"),
    col("prompt"),
    col("options", JSON),
    col("answer", Integer),
    col("labels", JSON),
    col("version", Integer),
)
papers = table("papers", fk("pub", "publications"), col("title"), col("items", JSON), col("created"))
attempts = table(
    "attempts",
    fk("paper", "papers"),
    fk("student", "users"),
    col("question"),
    col("seq", Integer),
    col("choice", Integer),
    col("correct", Boolean),
    col("cause"),
    col("seconds", Float),
    col("submission"),
    col("created"),
    UniqueConstraint("paper", "student", "question", "seq"),
    UniqueConstraint("paper", "student", "submission"),
)
uses = table(
    "resource_uses",
    fk("pub", "publications"),
    fk("version", "resource_versions"),
    fk("student", "users"),
    col("created"),
)
jobs = table(
    "jobs",
    fk("owner", "users"),
    col("kind"),
    col("state"),
    col("phase"),
    col("input", JSON),
    col("checkpoint", JSON),
    col("result", JSON),
    col("error", Text),
    col("created"),
    col("updated"),
)
audit = table(
    "audit", fk("actor", "users"), col("action"), col("object"), col("detail", Text), col("created")
)
settings = table("settings", col("value", JSON))
migrations = table("schema_migrations", col("applied"))


@contextmanager
def transaction(write=True):
    with engine.connect() as db:
        if write and not PG:
            db.exec_driver_sql("BEGIN IMMEDIATE")
        with_scope = db.get_transaction() or db.begin()
        try:
            yield db
            with_scope.commit()
            if changed := db.info.pop("classroom_changes", set()):
                from .live import invalidate

                for pub in changed:
                    invalidate(pub)
        except BaseException:
            db.info.pop("classroom_changes", None)
            with_scope.rollback()
            raise


def row(db, t, key, lock=False):
    stmt = select(t).where(t.c.id == key)
    if lock:
        stmt = stmt.with_for_update()
    item = db.execute(stmt).mappings().first()
    return dict(item) if item else None


def add(db, t, **fields):
    fields.setdefault("id", uid())
    db.execute(insert(t).values(**fields))
    return fields


def change(db, t, key, **fields):
    db.execute(update(t).where(t.c.id == key).values(**fields))


def rows(db, stmt):
    return [dict(r) for r in db.execute(stmt).mappings()]


def log(db, actor, action, object_id, detail=""):
    add(db, audit, actor=actor, action=action, object=object_id, detail=detail, created=now())


def password(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 180000).hex()


def migrate():
    with engine.begin() as db:
        if PG:
            db.execute(text("SELECT pg_advisory_xact_lock(731142)"))
        meta.create_all(db)
        if not row(db, migrations, "001"):
            if PG:
                db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                db.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(128)"))
            add(db, migrations, id="001", applied=now())
        if not row(db, migrations, "002"):
            add(db, migrations, id="002", applied=now())
