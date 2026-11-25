from collections import defaultdict
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from .access import STAFF, current, fail, group, pub_access, required, roles
from .db import add, attempts, now, papers, questions, row, rows, transaction, users, uses

router = APIRouter(prefix="/api")


class Question(BaseModel):
    point: str = Field(min_length=1, max_length=100)
    difficulty: str = Field(min_length=1, max_length=40)
    kind: str
    prompt: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=2, max_length=8)
    answer: int = Field(ge=0)
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def options_ok(self):
        if (
            self.kind not in {"选择题", "判断题"}
            or self.answer >= len(self.options)
            or (self.kind == "判断题" and len(self.options) != 2)
        ):
            raise ValueError("题型或标准答案无效")
        return self


@router.get("/questions")
def bank(point: str = "", difficulty: str = "", kind: str = "", user=Depends(current)):
    roles(user, STAFF)
    with transaction(False) as db:
        stmt = select(questions).where(questions.c.group_id == user["group_id"])
        for col, val in [
            (questions.c.point, point),
            (questions.c.difficulty, difficulty),
            (questions.c.kind, kind),
        ]:
            if val:
                stmt = stmt.where(col == val)
        return rows(db, stmt)


@router.post("/questions")
def new_question(data: Question, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        return add(db, questions, group_id=user["group_id"], version=1, **data.model_dump())


class Paper(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    ids: list[str] = Field(min_length=1, max_length=50)


def make_paper(db, user, pub, data):
    items = []
    for key in dict.fromkeys(data.ids):
        q = required(row(db, questions, key))
        group(user, q["group_id"])
        items.append(q)
    return add(db, papers, pub=pub, title=data.title, items=items, created=now())


@router.post("/classrooms/{key}/papers")
def assign(key: str, data: Paper, user=Depends(current)):
    roles(user, STAFF)
    with transaction() as db:
        pub_access(db, user, key, True, True)
        return make_paper(db, user, key, data)


@router.get("/classrooms/{key}/papers")
def paper_list(key: str, user=Depends(current)):
    with transaction(False) as db:
        pub_access(db, user, key)
        listing = rows(db, select(papers).where(papers.c.pub == key).order_by(papers.c.created.desc()))
        if user["role"] == "student":
            for p in listing:
                p["items"] = [
                    {k: v for k, v in q.items() if k not in ("answer", "labels")} for q in p["items"]
                ]
        return listing


class Answer(BaseModel):
    paper: str
    question: str
    choice: int = Field(ge=0)
    seconds: float = Field(ge=0, le=86400, allow_inf_nan=False)
    submission: str = Field(min_length=1, max_length=100)
    expected_seq: int = Field(ge=1)


def grade(db, user, payload):
    roles(user, {"student"})
    a = Answer(**payload)
    paper = required(row(db, papers, a.paper))
    pub_access(db, user, paper["pub"], True, True)
    q = next((q for q in paper["items"] if q["id"] == a.question), None) or fail(404, "试卷中无此题")
    old = (
        db.execute(
            select(attempts).where(
                attempts.c.paper == a.paper,
                attempts.c.student == user["id"],
                attempts.c.submission == a.submission,
            )
        )
        .mappings()
        .first()
    )
    if old:
        return dict(old)
    prev = (
        db.execute(
            select(attempts)
            .where(
                attempts.c.paper == a.paper,
                attempts.c.student == user["id"],
                attempts.c.question == a.question,
            )
            .order_by(attempts.c.seq.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    seq = (prev["seq"] + 1) if prev else 1
    if a.expected_seq != seq or (prev and prev["correct"]):
        fail(409, "该次作答已完成，请刷新记录")
    if a.choice >= len(q["options"]):
        fail(422, "选项超出题目范围")
    ok = a.choice == q["answer"]
    return add(
        db,
        attempts,
        paper=a.paper,
        student=user["id"],
        question=a.question,
        seq=seq,
        choice=a.choice,
        correct=ok,
        cause="" if ok else q["labels"].get(str(a.choice), q["point"]),
        seconds=a.seconds,
        submission=a.submission,
        created=now(),
    )


@router.get("/classrooms/{key}/attempts")
def answers(key: str, user=Depends(current)):
    with transaction(False) as db:
        pub_access(db, user, key)
        stmt = select(attempts).join(papers, papers.c.id == attempts.c.paper).where(papers.c.pub == key)
        if user["role"] == "student":
            stmt = stmt.where(attempts.c.student == user["id"])
        return rows(db, stmt.order_by(attempts.c.created))


class Analysis(BaseModel):
    pub: str
    point: str = ""
    student: str = ""
    start: str = ""
    end: str = ""


def analyze(db, user, payload):
    roles(user, STAFF | {"admin"})
    query = Analysis(**payload)
    pub = pub_access(db, user, query.pub)
    stmt = (
        select(attempts, papers.c["items"], papers.c.title, users.c.name)
        .join(papers, papers.c.id == attempts.c.paper)
        .join(users, users.c.id == attempts.c.student)
        .where(papers.c.pub == query.pub)
    )
    counts = select(uses).where(uses.c.pub == query.pub)
    for t, which in ((attempts, "answers"), (uses, "uses")):
        s = stmt if which == "answers" else counts
        if query.student:
            s = s.where(t.c.student == query.student)
        if query.start:
            s = s.where(t.c.created >= query.start)
        if query.end:
            s = s.where(t.c.created <= query.end + "T23:59:59.999999+00:00")
        if which == "answers":
            stmt = s
        else:
            counts = s
    points = defaultdict(
        lambda: {"first": 0, "first_correct": 0, "redo": 0, "redo_correct": 0, "seconds": 0, "uses": 0}
    )
    details = []
    for a in rows(db, stmt.order_by(attempts.c.created)):
        q = next(q for q in a.pop("items") if q["id"] == a["question"])
        if query.point and query.point != q["point"]:
            continue
        agg = points[q["point"]]
        bucket = "first" if a["seq"] == 1 else "redo"
        agg[bucket] += 1
        agg[bucket + "_correct"] += int(a["correct"])
        agg["seconds"] += a["seconds"]
        details.append(
            {
                **a,
                "prompt": q["prompt"],
                "point": q["point"],
                "chosen": q["options"][a["choice"]],
                "standard": q["options"][q["answer"]],
            }
        )
    materials = {v["id"]: v["point"] for v in pub["snapshot"]["resources"]}
    for usage in rows(db, counts):
        point = materials[usage["version"]]
        if not query.point or query.point == point:
            points[point]["uses"] += 1
    return {"points": dict(points), "details": details, "class_id": pub["class_id"]}
