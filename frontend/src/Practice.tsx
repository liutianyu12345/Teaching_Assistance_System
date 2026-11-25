import { useRef, useState } from "react";
import { api, task, token, type Row } from "./client";
import {
  Action,
  Empty,
  Field,
  Modal,
  Panel,
  Pill,
  useData,
  type PageProps,
} from "./widgets";
import { WithRoom } from "./Classroom";
import { Plot } from "./CircuitBoard";

export function Practice(p: PageProps) {
  return <WithRoom p={p}>{(room) => <Exercises p={p} room={room} />}</WithRoom>;
}
function Exercises({ p, room }: { p: PageProps; room: Row }) {
  const student = p.user.role === "student",
    base = "/classrooms/" + room.id;
  const papers = useData(base + "/papers", p.rev),
    attempts = useData(base + "/attempts", p.rev),
    bank = useData(student ? "" : "/questions", p.rev);
  const [wrong, W] = useState(false),
    [creating, C] = useState(false),
    [title, T] = useState("电流与电压 · 巩固练习"),
    [ids, I] = useState<string[]>([]),
    [filter, F] = useState<Row>({ point: "", difficulty: "", kind: "" }),
    [q, Q] = useState<Row | null>(null);
  const [choice, A] = useState<Record<string, number>>({}),
    starts = useRef<Record<string, number>>({}),
    tokens = useRef<Record<string, string>>({});
  const filtered: Row[] = (bank.data || []).filter((x: Row) =>
    Object.entries(filter).every(([k, v]) => !v || x[k] === v),
  );
  return (
    <>
      <div className="toolbar">
        {student ? (
          <div className="tabs">
            <button
              className={!wrong ? "selected" : ""}
              onClick={() => W(false)}
            >
              全部练习
            </button>
            <button className={wrong ? "selected" : ""} onClick={() => W(true)}>
              我的错题本
            </button>
          </div>
        ) : (
          <>
            <button
              className="primary"
              disabled={!room.active}
              onClick={() => C(true)}
            >
              ＋ 组卷并发布
            </button>
            <button
              onClick={() =>
                Q({
                  prompt: "",
                  point: "电流与电压的关系",
                  difficulty: "基础",
                  kind: "选择题",
                  options: "",
                  labels: "",
                  answer: 0,
                })
              }
            >
              录入题目
            </button>
          </>
        )}
      </div>
      {(papers.data || []).map((paper: Row) => {
        const items: Row[] = paper.items.filter(
          (item: Row) =>
            !wrong ||
            (attempts.data || []).some(
              (a: Row) =>
                a.paper === paper.id &&
                a.question === item.id &&
                a.seq === 1 &&
                !a.correct,
            ),
        );
        if (!items.length) return null;
        return (
          <Panel
            title={paper.title}
            key={paper.id}
            tools={<small>{items.length} 题</small>}
          >
            {items.map((item, i) => {
              const key = paper.id + item.id,
                history: Row[] = (attempts.data || []).filter(
                  (a: Row) => a.paper === paper.id && a.question === item.id,
                );
              const last = history.at(-1),
                seq = (last?.seq || 0) + 1,
                ak = key + seq;
              if (!starts.current[ak]) starts.current[ak] = Date.now();
              return (
                <article className="question" key={key}>
                  <small>
                    {item.point} · {item.kind} · {item.difficulty}
                  </small>
                  <h3>
                    {i + 1}. {item.prompt}
                  </h3>
                  <div className="choices">
                    {item.options.map((s: string, n: number) => (
                      <label
                        key={n}
                        className={choice[ak] === n ? "chosen" : ""}
                      >
                        {student ? (
                          <input
                            type="radio"
                            name={ak}
                            checked={choice[ak] === n}
                            disabled={!!last?.correct || !room.active}
                            onChange={() => A({ ...choice, [ak]: n })}
                          />
                        ) : (
                          <b>{String.fromCharCode(65 + n)}</b>
                        )}
                        {s}
                      </label>
                    ))}
                  </div>
                  {student ? (
                    <>
                      {history.map((a) => (
                        <small key={a.id}>
                          {a.seq === 1
                            ? "首次作答"
                            : "第 " + (a.seq - 1) + " 次重做"}{" "}
                          · {item.options[a.choice]} ·{" "}
                          {a.correct ? "正确" : "错误 · " + a.cause}
                        </small>
                      ))}
                      {!last?.correct && room.active && (
                        <Action
                          kind="primary"
                          disabled={choice[ak] === undefined}
                          run={async () => {
                            tokens.current[ak] ??= token();
                            await task("grade", {
                              paper: paper.id,
                              question: item.id,
                              choice: choice[ak],
                              submission: tokens.current[ak],
                              expected_seq: seq,
                              seconds: Math.min(
                                86400,
                                (Date.now() - starts.current[ak]) / 1000,
                              ),
                            });
                            p.refresh();
                          }}
                        >
                          {last ? "提交重做" : "提交答案"}
                        </Action>
                      )}
                    </>
                  ) : (
                    <small>标准答案 · {item.options[item.answer]}</small>
                  )}
                </article>
              );
            })}
          </Panel>
        );
      })}
      {(!papers.data?.length ||
        (wrong &&
          !(attempts.data || []).some(
            (a: Row) => a.seq === 1 && !a.correct,
          ))) && (
        <Empty>{wrong ? "暂无首次作答错误的题目" : "暂无已发布练习"}</Empty>
      )}
      {creating && (
        <Modal title="选择题目并组卷" close={() => C(false)}>
          <Field label="试卷名称">
            <input value={title} onChange={(e) => T(e.target.value)} />
          </Field>
          <div className="actions">
            {Object.entries({
              point: "知识点",
              difficulty: "难度",
              kind: "题型",
            }).map(([k, label]) => (
              <select
                key={k}
                value={filter[k]}
                aria-label={label}
                onChange={(e) => F({ ...filter, [k]: e.target.value })}
              >
                <option value="">全部{label}</option>
                {[
                  ...new Set<string>((bank.data || []).map((x: Row) => x[k])),
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            ))}
          </div>
          {filtered.map((x) => (
            <label className="check" key={x.id}>
              <input
                type="checkbox"
                checked={ids.includes(x.id)}
                onChange={() =>
                  I(
                    ids.includes(x.id)
                      ? ids.filter((id) => id !== x.id)
                      : [...ids, x.id],
                  )
                }
              />
              {x.prompt}
            </label>
          ))}
          <Action
            kind="primary"
            disabled={!ids.length}
            run={async () => {
              await api(base + "/papers", "POST", { title, ids });
              C(false);
              I([]);
              p.refresh();
            }}
          >
            发布 {ids.length} 道题
          </Action>
        </Modal>
      )}
      {q && (
        <Modal title="录入客观题" close={() => Q(null)}>
          {Object.entries({
            point: "知识点",
            prompt: "题干",
            options: "每行一个选项",
            labels: "每行一个选项错因（可留空）",
          }).map(([k, l]) => (
            <Field key={k} label={l}>
              <textarea
                value={q[k]}
                onChange={(e) => Q({ ...q, [k]: e.target.value })}
              />
            </Field>
          ))}
          <div className="actions">
            {Object.entries({
              kind: ["选择题", "判断题"],
              difficulty: ["基础", "提高", "综合"],
            }).map(([k, vs]) => (
              <select
                key={k}
                aria-label={k === "kind" ? "题型" : "难度"}
                value={q[k]}
                onChange={(e) => Q({ ...q, [k]: e.target.value })}
              >
                {vs.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            ))}
          </div>
          <Field label="正确选项序号（从 1 开始）">
            <input
              type="number"
              min="1"
              value={q.answer + 1}
              onChange={(e) => Q({ ...q, answer: +e.target.value - 1 })}
            />
          </Field>
          <Action
            kind="primary"
            run={async () => {
              const labels: Row = {};
              q.labels.split("\n").forEach((s: string, i: number) => {
                if (s.trim()) labels[i] = s.trim();
              });
              await api("/questions", "POST", {
                ...q,
                options: q.options
                  .split("\n")
                  .map((s: string) => s.trim())
                  .filter(Boolean),
                labels,
              });
              Q(null);
              p.refresh();
            }}
          >
            保存到题库
          </Action>
        </Modal>
      )}
    </>
  );
}
export function Analytics(p: PageProps) {
  return <WithRoom p={p}>{(room) => <Analysis p={p} room={room} />}</WithRoom>;
}
function Analysis({ p, room }: { p: PageProps; room: Row }) {
  const [f, F] = useState<Row>({ point: "", student: "", start: "", end: "" }),
    [data, D] = useState<Row | null>(null),
    [users, U] = useState<Row[]>([]);
  async function query() {
    const j = await task("analyze", { ...f, pub: room.id });
    D(j.result);
    if (!f.student && !f.point && !f.start && !f.end)
      U(
        Array.from(
          new Map<string, Row>(
            j.result.details.map((x: Row) => [x.student, x]),
          ).values(),
        ),
      );
  }
  const points = Object.entries(data?.points || {}) as [string, Row][];
  const pct = (c: number, n: number) => (n ? Math.round((100 * c) / n) : null);
  return (
    <>
      <Panel title="学情筛选">
        <div className="toolbar">
          <Field label="知识点">
            <input
              placeholder="全部知识点"
              value={f.point}
              onChange={(e) => F({ ...f, point: e.target.value })}
            />
          </Field>
          <Field label="学生">
            <select
              value={f.student}
              onChange={(e) => F({ ...f, student: e.target.value })}
            >
              <option value="">全班学生</option>
              {users.map((x) => (
                <option key={x.student} value={x.student}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          {["start", "end"].map((k, i) => (
            <Field key={k} label={i ? "结束日期" : "开始日期"}>
              <input
                type="date"
                value={f[k]}
                onChange={(e) => F({ ...f, [k]: e.target.value })}
              />
            </Field>
          ))}
          <Action kind="primary" run={query}>
            统计学情
          </Action>
        </div>
      </Panel>
      {data ? (
        <>
          <Panel title={"知识点表现 · " + data.class_id}>
            {points.length ? (
              <>
                <Plot
                  option={{
                    color: ["#15836d", "#db9355"],
                    grid: { left: 55, bottom: 45, top: 38, right: 18 },
                    legend: { top: 0 },
                    tooltip: {},
                    xAxis: { type: "category", data: points.map(([s]) => s) },
                    yAxis: {
                      type: "value",
                      max: 100,
                      axisLabel: { formatter: "{value}%" },
                    },
                    series: ["首次正确率", "重做正确率"].map((s, i) => ({
                      name: s,
                      type: "bar",
                      barMaxWidth: 38,
                      data: points.map(([, v]) =>
                        i
                          ? pct(v.redo_correct, v.redo)
                          : pct(v.first_correct, v.first),
                      ),
                    })),
                  }}
                />
                <table>
                  <thead>
                    <tr>
                      <th>知识点</th>
                      <th>首次正确 / 作答</th>
                      <th>重做正确 / 作答</th>
                      <th>平均耗时</th>
                      <th>资源阅读</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.map(([s, v]) => (
                      <tr key={s}>
                        <td>{s}</td>
                        <td>
                          {v.first_correct} / {v.first}
                        </td>
                        <td>
                          {v.redo_correct} / {v.redo}
                        </td>
                        <td>
                          {v.first + v.redo
                            ? (v.seconds / (v.first + v.redo)).toFixed(1) +
                              " 秒"
                            : "—"}
                        </td>
                        <td>{v.uses} 次</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <Empty>当前范围内暂无学习数据</Empty>
            )}
          </Panel>
          <Panel
            title="原始作答"
            tools={<button onClick={() => p.go("practice")}>追加练习 →</button>}
          >
            {data.details.map((a: Row) => (
              <div className="record" key={a.id}>
                <b>
                  {a.name} · {a.seq === 1 ? "首次作答" : "重做"}　
                </b>
                <Pill v={a.correct ? "正确" : "错误"} />
                <p>{a.prompt}</p>
                <small>
                  所选 · {a.chosen}　标准 · {a.standard}　{a.cause}
                </small>
              </div>
            ))}
          </Panel>
        </>
      ) : (
        <Empty>选择统计范围后，查看首次作答、重做结果和资源使用次数。</Empty>
      )}
    </>
  );
}
