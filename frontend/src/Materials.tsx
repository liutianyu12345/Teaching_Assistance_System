import { useState } from "react";
import { api, task, type Row } from "./client";
import {
  Action,
  Empty,
  ErrorLine,
  Field,
  Modal,
  Panel,
  Pill,
  useData,
  type PageProps,
} from "./widgets";
import { CircuitBoard } from "./CircuitBoard";
const blank = {
  title: "",
  kind: "实验指导",
  chapter: "九年级 · 欧姆定律",
  point: "电流与电压的关系",
  source: "教师原创",
  body: "",
};
export function Materials(p: PageProps) {
  const { data, error } = useData("/resources", p.rev),
    items: Row[] = data || [];
  const [query, Q] = useState(""),
    [filters, F] = useState<Row>({}),
    [editing, E] = useState<Row | null>(null),
    [file, SF] = useState<File | null>(null),
    [detail, D] = useState<Row | null>(null),
    [reason, R] = useState(""),
    [hits, H] = useState<Row[] | null>(null);
  const sources = useData(
    detail ? "/resources/" + detail.id + "/sources" : "",
    p.rev,
  );
  const owner = (v: Row) => v.owner === p.user.id,
    canCreate = ["teacher", "lead"].includes(p.user.role);
  const list = items.filter(
    (v) =>
      (v.title + v.body).includes(query) &&
      Object.entries(filters).every(([k, val]) => !val || v[k] === val),
  );
  async function review(v: Row, action: string) {
    await api("/resources/" + v.id + "/review", "POST", {
      action,
      feedback: reason,
    });
    D(null);
    R("");
    p.refresh();
    p.notify("资源已" + action);
  }
  function form(v: Row) {
    E(v);
    SF(null);
    D(null);
  }
  return (
    <>
      <div className="toolbar">
        <input
          placeholder="搜索资源标题或正文"
          value={query}
          onChange={(e) => {
            Q(e.target.value);
            H(null);
          }}
        />
        {[
          ["kind", "类型"],
          ["status", "状态"],
          ["chapter", "章节"],
          ["point", "知识点"],
        ].map(([k, s]) => (
          <select
            aria-label={s}
            value={filters[k] || ""}
            key={k}
            onChange={(e) => F({ ...filters, [k]: e.target.value })}
          >
            <option value="">全部{s}</option>
            {[...new Set(items.map((x) => x[k]))].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        ))}
        <Action
          run={async () =>
            H(await api("/knowledge?q=" + encodeURIComponent(query)))
          }
          disabled={!query}
        >
          检索知识片段
        </Action>
        {canCreate && (
          <button className="primary" onClick={() => form({ ...blank })}>
            ＋ 新建资源
          </button>
        )}
      </div>
      <ErrorLine value={error} />
      {hits && (
        <Panel
          title="知识片段来源"
          tools={<button onClick={() => H(null)}>收起</button>}
        >
          {hits.map((x, i) => (
            <div className="record" key={i}>
              <b>
                {x.title} · V{x.number}
              </b>
              <small>
                {x.source} · 第 {x.position + 1} 字起
              </small>
              <p>{x.body}</p>
            </div>
          ))}
        </Panel>
      )}
      <Panel title="资源版本" tools={<small>共 {list.length} 条</small>}>
        {list.map((v) => (
          <button
            className="listrow"
            key={v.id}
            onClick={() => {
              D(v);
              R("");
            }}
          >
            <span className="tile">▤</span>
            <span className="grow">
              <strong>{v.title}</strong>
              <small>
                {v.kind} · {v.chapter} · {v.point}
              </small>
            </span>
            <span className="mono">V{v.number}</span>
            <Pill v={v.status} />
          </button>
        ))}
        {!list.length && <Empty>暂无符合条件的资源</Empty>}
      </Panel>
      {detail && (
        <Modal title={detail.title} close={() => D(null)}>
          <p>
            <Pill v={detail.status} />
            　版本 V{detail.number} · {detail.source}
          </p>
          <p className="pre">{detail.body}</p>
          {detail.feedback && <p>审核意见 · {detail.feedback}</p>}
          {detail.config && (
            <CircuitBoard
              resistance={detail.config.resistance}
              voltage={detail.config.initial}
            />
          )}
          {(sources.data || []).map((s: Row) => (
            <div className="record" key={s.id}>
              <b>
                {s.title} · V{s.number}
              </b>
              <small>
                {s.source} · 第 {s.position + 1} 字起
              </small>
              <p>{s.excerpt}</p>
            </div>
          ))}
          {detail.filename && (
            <a href={"/api/resources/" + detail.id + "/file"}>
              下载 {detail.filename}
            </a>
          )}
          <div className="actions">
            {owner(detail) && (
              <button onClick={() => form({ ...detail })}>修订为新版本</button>
            )}
            {detail.status === "草稿" && owner(detail) && (
              <Action kind="primary" run={() => review(detail, "提交")}>
                提交审核
              </Action>
            )}
            {detail.status === "待审核" && (
              <>
                <Field label="退回意见">
                  <input value={reason} onChange={(e) => R(e.target.value)} />
                </Field>
                <Action run={() => review(detail, "退回")}>退回</Action>
                <Action kind="primary" run={() => review(detail, "通过")}>
                  审核通过并入库
                </Action>
              </>
            )}
            {(owner(detail) ||
              ["admin", "reviewer", "lead"].includes(p.user.role)) &&
              ["已发布", "已撤回"].includes(detail.status) && (
                <Action
                  run={() =>
                    review(detail, detail.status === "已发布" ? "撤回" : "归档")
                  }
                >
                  {detail.status === "已发布" ? "撤回版本" : "归档版本"}
                </Action>
              )}
          </div>
        </Modal>
      )}
      {editing && (
        <Modal
          title={editing.id ? "修订资源" : "新建资源"}
          close={() => E(null)}
        >
          <div className="formgrid">
            {Object.entries({
              title: "资源名称",
              kind: "类型",
              chapter: "教材章节",
              point: "知识点",
              source: "资源来源",
              body: "资源正文或可检索摘要",
            }).map(([key, label]) => (
              <Field key={key} label={label}>
                {key === "body" ? (
                  <textarea
                    value={editing[key]}
                    onChange={(e) => E({ ...editing, [key]: e.target.value })}
                  />
                ) : (
                  <input
                    value={editing[key]}
                    onChange={(e) => E({ ...editing, [key]: e.target.value })}
                  />
                )}
              </Field>
            ))}
            <Field label="附件（可选，最多 32 MB）">
              <input
                type="file"
                onChange={(e) => SF(e.target.files?.[0] || null)}
              />
            </Field>
          </div>
          <Action
            kind="primary"
            run={async () => {
              const v = await api(
                editing.id
                  ? "/resources/" + editing.id + "/revise"
                  : "/resources",
                "POST",
                editing,
              );
              if (file) {
                const fd = new FormData();
                fd.append("file", file);
                await api("/resources/" + v.id + "/file", "POST", fd);
              }
              E(null);
              p.refresh();
              p.notify("资源草稿已保存");
            }}
          >
            保存草稿
          </Action>
        </Modal>
      )}
    </>
  );
}
export function Generator(p: PageProps) {
  const [prompt, P] = useState(
      "固定电阻为 10 Ω，允许学生将电压从 0 V 调至 6 V，观察电流变化。",
    ),
    [job, J] = useState<Row | null>(null),
    [parent, Par] = useState(""),
    [v, V] = useState(1);
  const conf = job?.result?.config || job?.preview;
  return (
    <div className="two">
      <Panel title="实验设计要求">
        <Field label="描述教学目标、控制变量和电压范围">
          <textarea
            rows={6}
            value={prompt}
            onChange={(e) => P(e.target.value)}
          />
        </Field>
        {parent && <p className="note">正在基于上一次候选配置继续修改</p>}
        <div className="actions">
          <Action
            kind="primary"
            disabled={!prompt.trim()}
            run={async () => {
              J(null);
              const j = await task("generate", { prompt, parent }, J);
              J(j);
              V(j.result.config.initial);
              p.refresh();
            }}
          >
            生成候选演示
          </Action>
          {job && !["已取消", "失败", "完成"].includes(job.state) && (
            <Action run={() => api("/jobs/" + job.id + "/cancel", "POST")}>
              取消
            </Action>
          )}
        </div>
        {job && (
          <p>
            <Pill v={job.state} />　{job.phase}
          </p>
        )}
        {job?.state === "完成" && (
          <>
            <p>{job.result.mode} · 已进入资源审核队列</p>
            {job.result.reason && <small>{job.result.reason}</small>}
            <div className="actions">
              <button
                onClick={() => {
                  Par(job.id);
                  P("");
                }}
              >
                继续修改
              </button>
              <button onClick={() => p.go("library")}>前往审核</button>
            </div>
            <h3>依据材料</h3>
            {job.result.sources.map((s: Row, i: number) => (
              <div className="record" key={i}>
                {s.title} · V{s.number}
                <small>
                  {s.source} · 第 {s.position + 1} 字起
                </small>
              </div>
            ))}
          </>
        )}
      </Panel>
      <Panel title="电路预览">
        <CircuitBoard
          voltage={conf ? v : 1}
          resistance={conf?.resistance || 10}
        />
        {conf ? (
          <Field label={"试调电压　" + v + " V"}>
            <input
              type="range"
              min={conf.minimum}
              max={conf.maximum}
              step=".1"
              value={v}
              onChange={(e) => V(+e.target.value)}
            />
          </Field>
        ) : (
          <p className="note">当前显示本地示意。生成完成后可预览候选参数。</p>
        )}
        {conf && (
          <p className="mono">
            I = U / R = {v} / {conf.resistance} ={" "}
            {+(v / conf.resistance).toFixed(6)} A
          </p>
        )}
      </Panel>
    </div>
  );
}
