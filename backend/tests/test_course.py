import json
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from zipfile import ZipFile
import httpx
import pytest
from app.physics import Circuit


def ok(response):
    assert response.is_success, response.text
    return response.json()


def wait_job(client, job):
    for _ in range(180):
        j = ok(client.get("/api/jobs/" + job))
        if j["state"] in ("完成", "失败", "已取消"):
            return j
        time.sleep(0.1)
    pytest.fail("task did not complete")


def job(client, kind, data):
    key = ok(client.post("/api/jobs/" + kind, json=data))["id"]
    j = wait_job(client, key)
    assert j["state"] == "完成", j["error"]
    return j


def room(client):
    return ok(client.get("/api/classrooms"))[-1]


def test_physics_and_student_isolation(login):
    a, b, other, t = [login(x) for x in ("student1", "student2", "student3", "teacher")]
    p = room(t)
    path = "/api/classrooms/" + p["id"]
    assert other.get(path + "/records").status_code == 403
    assert other.get("/api/classrooms").json() == []
    assert a.get("/api/resources").status_code == 403

    def submit(client, v, key):
        return client.post(
            path + "/observations", json={"voltage": v, "submission": key, "note": "观察电表"}
        )

    assert ok(submit(a, 1, "A1"))["current"] == 0.1
    assert ok(submit(a, 1, "A1"))["current"] == 0.1
    assert ok(submit(b, 3, "B1"))["current"] == 0.3
    assert submit(b, 9, "B2").status_code == 422
    assert len(ok(a.get(path + "/records"))["observations"]) == 1
    assert {r["student"] for r in ok(t.get(path + "/records"))["observations"]} == {
        "student1",
        "student2",
    }
    ok(a.post(path + "/report", json={"body": "定值电阻下电流与电压成正比。"}))
    assert ok(b.get(path + "/records"))["reports"] == []
    assert ok(t.get(path + "/records"))["reports"][0]["name"] == "张明"
    assert Circuit(resistance=10).reading(3) == 0.3
    with pytest.raises(ValueError):
        Circuit(resistance=0)
    with pytest.raises(ValueError):
        Circuit(current_unit="mA")


def test_resource_versions_collaboration_and_publication(login):
    teacher, peer, reviewer, student = [
        login(x) for x in ("teacher", "colleague", "reviewer", "student1")
    ]
    materials = ok(teacher.get("/api/resources"))
    exp = next(v for v in materials if v["config"] and v["status"] == "已发布")
    payload = {
        "title": "实验记录附件",
        "kind": "实验指导",
        "chapter": "电学",
        "point": "电流",
        "source": "教师编写",
        "body": "保持电阻不变，测量电流",
    }
    v = ok(teacher.post("/api/resources", json=payload))
    ok(
        teacher.post(
            "/api/resources/" + v["id"] + "/file", files={"file": ("notes.txt", b"pinned text")}
        )
    )
    assert teacher.post("/api/lessons", json={"title": "未审", "refs": [v["id"]]}).status_code == 409
    api = "/api/resources/" + v["id"] + "/review"
    ok(teacher.post(api, json={"action": "提交"}))
    ok(reviewer.post(api, json={"action": "通过"}))
    hits = ok(teacher.get("/api/knowledge", params={"q": "测量电流"}))
    assert any(x["version"] == v["id"] and x["position"] == 0 for x in hits)
    lesson = ok(
        teacher.post(
            "/api/lessons",
            json={"title": "协作测试课", "refs": [exp["id"], v["id"]], "collabs": ["colleague"]},
        )
    )
    path = "/api/lessons/" + lesson["id"]
    original = lesson["sections"]["实验"]
    edited = ok(
        peer.put(
            path + "/section", json={"section": "实验", "text": "记录三组电流", "rev": original["rev"]}
        )
    )
    conflict = teacher.put(
        path + "/section", json={"section": "实验", "text": "覆盖", "rev": original["rev"]}
    )
    assert (
        conflict.status_code == 409 and conflict.json()["detail"]["current"]["text"] == "记录三组电流"
    )
    ok(peer.post(path + "/comments", json={"section": "实验", "body": "建议先调零"}))
    assert len(ok(teacher.get(path + "/comments"))) == 1
    final = ok(teacher.post(path + "/finalize", json={"rev": edited["rev"]}))
    pub = ok(teacher.post(path + "/publish", json={"class_id": "九年级一班", "rev": final["rev"]}))
    p = "/api/classrooms/" + pub["id"]
    ok(
        teacher.put(
            path + "/section",
            json={"section": "实验", "text": "新草稿", "rev": edited["sections"]["实验"]["rev"]},
        )
    )
    ok(teacher.post(api, json={"action": "撤回"}))
    assert (
        ok(student.get("/api/classrooms"))[0]["snapshot"]["sections"]["实验"]["text"] == "记录三组电流"
    )
    assert student.get(p + "/materials/" + v["id"] + "/file").content == b"pinned text"
    versions = ok(teacher.get(path + "/history"))
    restored = ok(teacher.post(path + "/restore/1", json={"rev": versions[0]["rev"]}))
    assert restored["rev"] > versions[0]["rev"] and restored["state"] == "草稿"
    new = ok(teacher.post("/api/resources/" + v["id"] + "/revise", json={**payload, "body": "新材料"}))
    assert new["number"] == 2 and new["resource"] == v["resource"]
    ok(teacher.post(p + "/withdraw"))
    assert student.post(p + "/report", json={"body": "迟交"}).status_code == 409


def test_live_duplicate_deadline_and_reconnect(login):
    t, s = login("teacher"), login("student1")
    p = room(t)
    path = "/api/classrooms/" + p["id"]
    a = ok(
        t.post(
            path + "/activities",
            json={"kind": "投票", "prompt": "电流变化？", "options": ["增大", "减小"]},
        )
    )
    sub = "/api/activities/" + a["id"]
    with s.websocket_connect("/api/ws/classrooms/" + p["id"]) as ws:
        assert ws.receive_json()["activities"][0]["state"] == "开放"
    with ThreadPoolExecutor(2) as pool:
        values = list(pool.map(lambda _: ok(s.post(sub + "/answer", json={"body": "增大"})), range(2)))
    assert values[0]["id"] == values[1]["id"]
    ok(t.post(sub + "/state/截止"))
    with s.websocket_connect("/api/ws/classrooms/" + p["id"]) as ws:
        data = ws.receive_json()["activities"][0]
        assert (data["state"], data["count"], data["mine"]) == ("截止", 1, "增大")
    assert login("student2").post(sub + "/answer", json={"body": "减小"}).status_code == 409


def test_grade_redo_trace_and_stats(login):
    t, s = login("teacher"), login("student1")
    p = room(t)
    path = "/api/classrooms/" + p["id"]
    source = ok(t.get("/api/questions"))[0]
    paper = ok(t.post(path + "/papers", json={"title": "判分验证", "ids": [source["id"]]}))
    q = next(x for x in ok(s.get(path + "/papers")) if x["id"] == paper["id"])["items"][0]
    assert "answer" not in q and "labels" not in q
    a = {
        "paper": paper["id"],
        "question": q["id"],
        "choice": (source["answer"] + 1) % len(q["options"]),
        "seconds": 3,
        "submission": "first",
        "expected_seq": 1,
    }
    first = job(s, "grade", a)["result"]
    assert first["seq"] == 1 and not first["correct"] and first["cause"]
    assert job(s, "grade", a)["result"]["id"] == first["id"]
    redo = job(
        s, "grade", {**a, "expected_seq": 2, "choice": source["answer"], "submission": "second"}
    )["result"]
    assert redo["correct"] and redo["seq"] == 2
    v = p["snapshot"]["resources"][0]
    ok(s.post(path + "/materials/" + v["id"] + "/open"))
    stats = job(t, "analyze", {"pub": p["id"], "student": "student1"})["result"]
    values = stats["points"][source["point"]]
    assert [values[k] for k in ("first", "first_correct", "redo", "redo_correct", "uses")] == [
        1,
        0,
        1,
        1,
        1,
    ]
    assert len(stats["details"]) == 2 and stats["details"][0]["prompt"] == source["prompt"]


def test_generation_timeout_review_multiturn_and_export(login, monkeypatch):
    t = login("teacher")
    monkeypatch.setenv("MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("MODEL_NAME", "fixture")

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("test")

    from app import generation

    # Replace only the model transport, preserving the TestClient's HTTP methods.
    class TimedOut:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        post = timeout

    monkeypatch.setattr(generation.httpx, "Client", TimedOut)
    j = job(t, "generate", {"prompt": "固定电阻并绘图"})
    assert j["result"]["mode"] == "本地模板" and "ReadTimeout" in j["result"]["reason"]
    candidate = next(x for x in ok(t.get("/api/resources")) if x["id"] == j["result"]["version"])
    assert candidate["status"] == "待审核" and j["result"]["sources"]
    j2 = job(t, "generate", {"prompt": "将电压上限改为 4 V", "parent": j["id"]})
    assert j2["result"]["resource"] == j["result"]["resource"]
    stream = t.get("/api/jobs/" + j["id"] + "/stream")
    assert "data: " in stream.text and "完成" in stream.text
    for form in ("docx", "pdf"):
        exp = job(t, "export", {"lesson": room(t)["lesson"], "format": form})
        content = t.get("/api/jobs/" + exp["id"] + "/file").content
        if form == "pdf":
            assert content.startswith(b"%PDF")
        else:
            assert "word/document.xml" in ZipFile(BytesIO(content)).namelist()


def test_cancel_resume_and_admin(login, monkeypatch):
    from app import tasks

    t = login("teacher")
    original = tasks.dispatch
    monkeypatch.setattr(tasks, "dispatch", lambda key: None)
    j = ok(t.post("/api/jobs/generate", json={"prompt": "离线检查点恢复"}))["id"]
    ok(t.post("/api/jobs/" + j + "/cancel"))
    assert ok(t.get("/api/jobs/" + j))["state"] == "已取消"
    monkeypatch.setattr(tasks, "dispatch", original)
    ok(t.post("/api/jobs/" + j + "/resume"))
    assert wait_job(t, j)["state"] == "完成"
    assert login("student1").get("/api/jobs/" + j).status_code == 403
    admin = login("admin")
    assert ok(admin.get("/api/settings"))["repair_limit"] == 2
    assert any(x["action"] == "恢复任务" for x in ok(admin.get("/api/audit")))


def test_model_repair_and_persistent_citations(login, monkeypatch):
    from app import generation

    monkeypatch.setenv("MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("MODEL_NAME", "fixture")
    calls = []

    class Model:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            calls.append(kwargs["json"]["messages"])
            candidate = Circuit().model_dump()
            candidate["maximum"] = -1 if len(calls) == 1 else 4
            content = json.dumps(candidate, ensure_ascii=False)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(generation.httpx, "Client", Model)
    t = login("teacher")
    j = job(t, "generate", {"prompt": "将电压上限设置为 4 V"})
    assert len(calls) == 2 and j["result"]["mode"] == "模型生成"
    assert j["result"]["config"]["maximum"] == 4
    sources = ok(login("reviewer").get("/api/resources/" + j["result"]["version"] + "/sources"))
    assert sources and sources[0]["source_version"] and sources[0]["excerpt"]


def test_group_discussion_and_class_boundary(login):
    t, a, b, outside = [login(x) for x in ("teacher", "student1", "student2", "student3")]
    path = "/api/classrooms/" + room(t)["id"]
    activity = ok(t.post(path + "/activities", json={"kind": "分组讨论", "prompt": "比较两组实验数据"}))
    route = "/api/activities/" + activity["id"] + "/discuss"
    msg = {"body": "电流增大了三倍", "submission": "m1"}
    first = ok(a.post(route, json=msg))
    assert ok(a.post(route, json=msg))["id"] == first["id"]
    ok(b.post(route, json={**msg, "body": "电压也增大了三倍"}))
    assert outside.post(route, json=msg).status_code == 403
    record = ok(b.get(path + "/activities"))[0]
    assert record["team"] == "第 1 组" and record["count"] == 2 and len(record["messages"]) == 2
