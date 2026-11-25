import os
from sqlalchemy import select, text
from .db import PG, add, log, password, questions, row, settings, transaction, users
from .access import DEMO
from .physics import Circuit
from .resources import Material, make_version
from .lessons import LessonInput, create_lesson, update_lesson, publish
from .practice import Paper, make_paper

TOPIC = "电流与电压的关系"
CHAPTER = "九年级 · 欧姆定律"


def seed():
    with transaction() as db:
        if PG:
            db.execute(text("SELECT pg_advisory_xact_lock(731143)"))
        if not row(db, settings, "generation"):
            add(db, settings, id="generation", value={"repair_limit": 2, "timeout": 18})
        if db.scalar(select(users.c.id).limit(1)):
            return
        if not DEMO:
            secret = os.getenv("ADMIN_PASSWORD", "")
            if len(secret) < 12:
                raise RuntimeError("首次启动须设置至少 12 位的 ADMIN_PASSWORD")
            add(
                db,
                users,
                id="admin",
                username="admin",
                name="系统管理员",
                role="admin",
                group_id="物理教研组",
                classes=[],
                active=True,
                password=password(secret),
            )
            return
        for login, name, role, classes_ in [
            ("teacher", "林老师", "teacher", ["九年级一班"]),
            ("colleague", "陈老师", "teacher", ["九年级一班"]),
            ("lead", "周组长", "lead", ["九年级一班"]),
            ("reviewer", "审核教师", "reviewer", []),
            ("admin", "系统管理员", "admin", []),
            ("student1", "张明", "student", ["九年级一班"]),
            ("student2", "李悦", "student", ["九年级一班"]),
            ("student3", "王晨", "student", ["九年级二班"]),
        ]:
            add(
                db,
                users,
                id=login,
                username=login,
                name=name,
                role=role,
                group_id="物理教研组",
                classes=classes_,
                password=password("Physics2027!"),
                active=True,
            )
        teacher = row(db, users, "teacher")
        materials = []
        for title, kind, body, config in [
            (
                "定值电阻伏安实验",
                "交互演示",
                "保持电阻不变，调节电压。根据 I = U / R 计算电流，将三组数据绘为伏安曲线。",
                Circuit(),
            ),
            (
                "电流与电压探究记录单",
                "实验指导",
                "记录电压 U / V、电流 I / A 与固定电阻 R / Ω，比较数据并写出结论。",
                None,
            ),
            (
                "控制变量法教学设计",
                "教案",
                "从电路中电流变化的现象出发，明确改变、测量和保持不变的物理量。",
                None,
            ),
        ]:
            v = make_version(
                db,
                teacher,
                Material(
                    title=title,
                    kind=kind,
                    chapter=CHAPTER,
                    point=TOPIC,
                    source="本课例原创示范材料",
                    body=body,
                    config=config,
                ),
                status="已发布",
            )
            log(db, "reviewer", "审核示范材料", v["id"])
            materials.append(v["id"])
        ls = create_lesson(
            db,
            teacher,
            LessonInput(title="探究电流与电压的关系", refs=materials, collabs=["colleague", "lead"]),
        )
        ls = update_lesson(db, ls, teacher, state="定稿")
        p = publish(db, teacher, ls, "九年级一班")
        ids = []
        for prompt, opts, answer, labels in [
            (
                "定值电阻为 10 Ω，当两端电压为 3 V 时，通过它的电流是多少？",
                ["0.3 A", "3 A", "30 A"],
                0,
                {"1": "忽略电阻值", "2": "将除法误用为乘法"},
            ),
            (
                "探究电流与电压的关系时，应保持哪个物理量不变？",
                ["电流", "电压", "电阻"],
                2,
                {"0": "混淆因变量和控制变量", "1": "混淆自变量和控制变量"},
            ),
            (
                "电阻一定时，电压增大一倍，电流也增大一倍。",
                ["正确", "错误"],
                0,
                {"1": "未理解正比关系"},
            ),
        ]:
            q = add(
                db,
                questions,
                group_id=teacher["group_id"],
                point=TOPIC,
                difficulty="基础",
                kind="判断题" if len(opts) == 2 else "选择题",
                prompt=prompt,
                options=opts,
                answer=answer,
                labels=labels,
                version=1,
            )
            ids.append(q["id"])
        make_paper(db, teacher, p["id"], Paper(title="欧姆定律 · 随堂巩固", ids=ids[:2]))
