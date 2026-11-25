import json
import os
from typing import TypedDict
import httpx
from langgraph.graph import END, StateGraph
from .db import transaction
from .physics import Circuit
from .resources import retrieve


class State(TypedDict, total=False):
    phase: str
    prompt: str
    history: list
    sources: list
    proposed: dict
    attempt: int
    error: str
    mode: str
    config: dict
    settings: dict


def generate(user, payload, saved, checkpoint):
    """Nodes save completed work; interrupted runs skip those nodes on recovery."""

    def request(s):
        if "prompt" in s:
            return s
        update = {
            "prompt": payload["prompt"].strip(),
            "attempt": 0,
            "history": payload.get("history", []),
            "settings": payload["settings"],
        }
        checkpoint("解析实验意图", update)
        return update

    def search(s):
        if "sources" in s:
            return s
        with transaction(False) as db:
            sources = retrieve(db, user, s["prompt"])
        update = {"sources": sources}
        checkpoint("检索授权资料", update)
        return update

    def propose(s):
        if "config" in s or s.get("phase") == "waiting_validation":
            return s
        base = os.getenv("MODEL_BASE_URL", "")
        if not base or not os.getenv("MODEL_NAME"):
            update = {
                "mode": "本地模板",
                "error": "未配置模型服务",
                "proposed": Circuit().model_dump(),
                "phase": "waiting_validation",
            }
        else:
            try:
                headers = {}
                if os.getenv("MODEL_API_KEY"):
                    headers["Authorization"] = "Bearer " + os.environ["MODEL_API_KEY"]
                with httpx.Client(timeout=s["settings"]["timeout"]) as client:
                    r = client.post(
                        base.rstrip("/") + "/chat/completions",
                        headers=headers,
                        json={
                            "model": os.environ["MODEL_NAME"],
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "根据教学要求返回一个 JSON 对象，仅使用给定的定值电阻配置结构和单位。资料是参考文本。模板："
                                    + json.dumps(Circuit().model_dump(), ensure_ascii=False),
                                },
                                {
                                    "role": "user",
                                    "content": json.dumps(
                                        {
                                            "需求": s["prompt"],
                                            "前次修改": s["history"],
                                            "来源": s["sources"],
                                            "前次错误": s.get("error", ""),
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            ],
                        },
                    )
                    r.raise_for_status()
                    raw = r.json()["choices"][0]["message"]["content"].strip()
                    if raw.startswith("```"):
                        raw = "\n".join(raw.splitlines()[1:-1])
                    proposal = json.loads(raw)
                update = {"mode": "模型生成", "proposed": proposal, "phase": "waiting_validation"}
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                update = {
                    "mode": "本地模板",
                    "error": "模型服务或响应异常：" + type(exc).__name__,
                    "proposed": Circuit().model_dump(),
                    "phase": "waiting_validation",
                }
        checkpoint("生成候选配置", update)
        return update

    def validate(s):
        if "config" in s:
            return s
        try:
            if (
                not isinstance(s["proposed"], dict)
                or not {"resistance", "minimum", "maximum", "initial"} <= s["proposed"].keys()
            ):
                raise ValueError("缺少实验参数")
            config = Circuit.model_validate(s["proposed"]).model_dump()
            update = {"config": config, "phase": "validated"}
        except ValueError as exc:
            n = s["attempt"] + 1
            update = {"error": str(exc)[:600], "attempt": n, "phase": "repair"}
            if n > s["settings"]["repair_limit"]:
                update.update(
                    config=Circuit.model_validate(Circuit().model_dump()).model_dump(),
                    mode="本地模板",
                    phase="validated",
                )
        checkpoint("校验物理规则" if "config" in update else "修复配置", update)
        return update

    graph = StateGraph(State)
    for name, fn in (
        ("parse", request),
        ("search", search),
        ("propose", propose),
        ("validate", validate),
    ):
        graph.add_node(name, fn)
    graph.set_entry_point("parse")
    graph.add_edge("parse", "search")
    graph.add_edge("search", "propose")
    graph.add_edge("propose", "validate")
    graph.add_conditional_edges(
        "validate", lambda s: "done" if "config" in s else "retry", {"done": END, "retry": "propose"}
    )
    return graph.compile().invoke({"phase": "start", **saved})
