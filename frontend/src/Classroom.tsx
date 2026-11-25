import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, token, type Row } from "./client";
import {
  Action,
  Empty,
  ErrorLine,
  Field,
  Modal,
  Panel,
  Picker,
  Pill,
  useData,
  type PageProps,
} from "./widgets";
import { CircuitBoard, Plot } from "./CircuitBoard";

export function WithRoom({
  p,
  children,
}: {
  p: PageProps;
  children: (room: Row) => ReactNode;
}) {
  const rooms = useData("/classrooms", p.rev),
    [id, S] = useState(sessionStorage.getItem("room:" + p.user.id) || "");
  const room = rooms.data?.find((r: Row) => r.id === id) || rooms.data?.[0];
  return (
    <>
      <ErrorLine value={rooms.error} />
      {room ? (
        <>
          <div className="toolbar">
            <Picker
              label="班级课例"
              items={rooms.data}
              id={room.id}
              set={(v) => {
                S(v);
                sessionStorage.setItem("room:" + p.user.id, v);
              }}
            />
            <Pill v={room.active ? "已发布" : "已撤回"} />
          </div>
          <div key={room.id}>{children(room)}</div>
        </>
      ) : (
        <Empty>{rooms.data ? "暂无分配给此账号的课堂" : "正在读取课堂…"}</Empty>
      )}
    </>
  );
}
export function Classroom(p: PageProps) {
  return <WithRoom p={p}>{(room) => <Room p={p} room={room} />}</WithRoom>;
}
function Room({ p, room }: { p: PageProps; room: Row }) {
  const c = room.snapshot.config,
    student = p.user.role === "student",
    path = "/classrooms/" + room.id;
  const [v, V] = useState<number>(c.initial),
    [note, N] = useState(""),
    [report, R] = useState(""),
    [tab, T] = useState("实验台"),
    [acts, A] = useState<Row[]>([]),
    [active, Active] = useState(room.active),
    [connection, Conn] = useState("连接中"),
    [kind, K] = useState("投票"),
    [prompt, P] = useState("电阻不变，电压增大一倍，电流如何变化？"),
    [opts, O] = useState("增大一倍，保持不变，减小一半"),
    [feedback, F] = useState<Record<string, string>>({}),
    [opened, M] = useState<Row | null>(null),
    [withdraw, W] = useState(false);
  const records = useData(path + "/records", p.rev),
    submission = useRef(token());
  const amps = +(v / c.resistance).toFixed(8);
  useEffect(() => {
    let live = true,
      ws: WebSocket,
      timer: ReturnType<typeof setTimeout>;
    function connect() {
      if (!live) return;
      ws = new WebSocket(
        (location.protocol === "https:" ? "wss://" : "ws://") +
          location.host +
          "/api/ws/classrooms/" +
          room.id,
      );
      ws.onmessage = (e) => {
        if (live) {
          const d = JSON.parse(e.data);
          A(d.activities);
          Active(d.active);
          Conn("实时同步");
        }
      };
      ws.onclose = () => {
        if (live) {
          Conn("正在重连");
          timer = setTimeout(connect, 1500);
        }
      };
    }
    api(path + "/activities")
      .then((a) => {
        if (live) A(a);
      })
      .catch(() => {});
    connect();
    return () => {
      live = false;
      clearTimeout(timer);
      if (ws) ws.close();
    };
  }, [room.id, path]);
  const observations: Row[] = records.data?.observations || [];
  const curve = {
    color: ["#147963", "#d98b45"],
    grid: { left: 49, right: 25, top: 20, bottom: 42 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      name: "U / V",
      nameLocation: "middle",
      nameGap: 25,
      min: c.minimum,
      max: c.maximum,
    },
    yAxis: { type: "value", name: "I / A" },
    series: [
      {
        type: "line",
        showSymbol: false,
        data: [
          [c.minimum, c.minimum / c.resistance],
          [c.maximum, c.maximum / c.resistance],
        ],
      },
      {
        type: "line",
        showSymbol: true,
        symbolSize: 10,
        lineStyle: { opacity: 0 },
        data: [[v, amps]],
      },
    ],
  };
  async function sync() {
    A(await api(path + "/activities"));
    p.refresh();
  }
  return (
    <>
      <div className="tabs">
        {["实验台", "课堂互动", "过程记录", "课堂材料"].map((s) => (
          <button
            className={s === tab ? "selected" : ""}
            key={s}
            onClick={() => T(s)}
          >
            {s}
          </button>
        ))}
      </div>
      {tab === "实验台" && (
        <div className="two">
          <Panel
            title="定值电阻实验"
            tools={<span className="mono">R = {c.resistance} Ω</span>}
          >
            <CircuitBoard voltage={v} resistance={c.resistance} />
            <div className="readings">
              <div>
                <small>电源电压</small>
                <strong>
                  {v} <i>V</i>
                </strong>
              </div>
              <div>
                <small>电流读数</small>
                <strong>
                  {amps} <i>A</i>
                </strong>
              </div>
            </div>
            <Field label={"调节电压　" + c.minimum + " — " + c.maximum + " V"}>
              <input
                aria-label="调节电压"
                type="range"
                min={c.minimum}
                max={c.maximum}
                step=".1"
                value={v}
                onChange={(e) => V(+e.target.value)}
              />
            </Field>
            <p className="mono">
              I = U / R = {v} / {c.resistance} = {amps} A
            </p>
            {student && active && (
              <>
                <Field label="观察备注">
                  <input
                    value={note}
                    onChange={(e) => N(e.target.value)}
                    placeholder="描述电压变化及对应现象"
                  />
                </Field>
                <Action
                  kind="primary"
                  run={async () => {
                    await api(path + "/observations", "POST", {
                      voltage: v,
                      note,
                      submission: submission.current,
                    });
                    submission.current = token();
                    N("");
                    p.refresh();
                    p.notify("已记录本组数据");
                  }}
                >
                  记录这组数据
                </Action>
              </>
            )}
          </Panel>
          <div className="stack">
            <Panel title="电流随电压的变化">
              <Plot option={curve} />
            </Panel>
            <Panel title={student ? "我的探究结论" : "课堂任务"}>
              <p>{room.snapshot.sections["实验"].text}</p>
              {student && active && (
                <>
                  <textarea
                    value={report}
                    onChange={(e) => R(e.target.value)}
                    placeholder="结合测量数据写下结论及成立条件"
                  />
                  <Action
                    disabled={!report.trim()}
                    run={async () => {
                      await api(path + "/report", "POST", { body: report });
                      p.refresh();
                      p.notify("探究报告已提交");
                    }}
                  >
                    提交探究报告
                  </Action>
                </>
              )}
              {!student && room.teacher === p.user.id && active && (
                <button onClick={() => W(true)}>撤回课堂</button>
              )}
            </Panel>
          </div>
        </div>
      )}
      {tab === "过程记录" && (
        <div className="two">
          <Panel
            title="观察记录"
            tools={<button onClick={p.refresh}>刷新</button>}
          >
            {observations.length ? (
              <table>
                <thead>
                  <tr>
                    <th>学生</th>
                    <th>电压</th>
                    <th>电流</th>
                    <th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {observations.map((o) => (
                    <tr key={o.id}>
                      <td>{o.name}</td>
                      <td>{o.voltage} V</td>
                      <td>{o.current} A</td>
                      <td>{o.note || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>还没有实验观察记录</Empty>
            )}
          </Panel>
          <Panel title="探究报告">
            {(records.data?.reports || []).map((r: Row) => (
              <div className="record" key={r.id}>
                <b>{r.name}</b>
                <p>{r.body}</p>
              </div>
            ))}
            {!records.data?.reports?.length && <Empty>还没有提交的报告</Empty>}
          </Panel>
        </div>
      )}
      {tab === "课堂材料" && (
        <Panel title={"备课版本 V" + room.snapshot.lesson_rev + " 引用的材料"}>
          {room.snapshot.resources.map((m: Row) => (
            <div className="listrow" key={m.id}>
              <span className="grow">
                <strong>{m.title}</strong>
                <small>
                  {m.kind} · V{m.number} · {m.source}
                </small>
              </span>
              <Action
                disabled={!active}
                run={async () => {
                  await api(path + "/materials/" + m.id + "/open", "POST");
                  M(m);
                }}
              >
                阅读
              </Action>
            </div>
          ))}
        </Panel>
      )}
      {tab === "课堂互动" && (
        <div className="stack">
          {!student && active && (
            <Panel title="发起课堂活动">
              <div className="formgrid">
                <Field label="活动类型">
                  <select value={kind} onChange={(e) => K(e.target.value)}>
                    {[
                      "投票",
                      "选择题",
                      "判断题",
                      "抢答",
                      "分组讨论",
                      "随机点名",
                    ].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="活动问题">
                  <input value={prompt} onChange={(e) => P(e.target.value)} />
                </Field>
                {["投票", "选择题"].includes(kind) && (
                  <Field label="选项（用逗号分隔）">
                    <input value={opts} onChange={(e) => O(e.target.value)} />
                  </Field>
                )}
              </div>
              <Action
                kind="primary"
                run={async () => {
                  await api(path + "/activities", "POST", {
                    kind,
                    prompt,
                    options: opts
                      .split(/[,，]/)
                      .map((x) => x.trim())
                      .filter(Boolean),
                  });
                  await sync();
                }}
              >
                发起活动
              </Action>
            </Panel>
          )}
          <Panel title="课堂活动" tools={<Pill v={connection} />}>
            {acts.map((a) => (
              <article className="record" key={a.id}>
                <div className="panelhead">
                  <h3>{a.prompt}</h3>
                  <Pill v={a.state} />
                </div>
                <small>
                  {a.kind} · {a.count} 人提交{" "}
                  {a.kind === "随机点名" ? " · " + a.options.join("") : ""}
                </small>
                {Object.entries(a.counts).map(([s, n]) => (
                  <span className="chip" key={s}>
                    {s} · {String(n)}
                  </span>
                ))}
                {student && (
                  <>
                    {a.mine && <p>我的提交 · {a.mine}</p>}
                    {active && a.state === "开放" && !a.mine && (
                      <div className="actions">
                        {["投票", "选择题", "判断题"].includes(a.kind) ? (
                          a.options.map((s: string) => (
                            <Action
                              key={s}
                              run={async () => {
                                await api(
                                  "/activities/" + a.id + "/answer",
                                  "POST",
                                  { body: s },
                                );
                                await sync();
                              }}
                            >
                              {s}
                            </Action>
                          ))
                        ) : (
                          <>
                            <input
                              value={feedback[a.id] || ""}
                              onChange={(e) =>
                                F({ ...feedback, [a.id]: e.target.value })
                              }
                              placeholder={
                                a.kind === "分组讨论"
                                  ? "组别与讨论结论"
                                  : "抢答内容"
                              }
                            />
                            <Action
                              run={async () => {
                                const discussion = a.kind === "分组讨论";
                                await api(
                                  "/activities/" +
                                    a.id +
                                    (discussion ? "/discuss" : "/answer"),
                                  "POST",
                                  {
                                    body:
                                      feedback[a.id] ||
                                      (discussion ? "" : "参与抢答"),
                                    submission: token(),
                                  },
                                );
                                F({ ...feedback, [a.id]: "" });
                                await sync();
                              }}
                            >
                              提交
                            </Action>
                          </>
                        )}
                      </div>
                    )}
                  </>
                )}
                {a.kind === "分组讨论" && (
                  <div className="record">
                    {a.team && <b>{a.team}</b>}
                    {a.messages?.map((m: Row) => (
                      <p key={m.id}>
                        <small>
                          {m.team} · {m.name}
                        </small>
                        {m.body}
                      </p>
                    ))}
                  </div>
                )}
                {!student && active && a.state !== "已结束" && (
                  <div className="actions">
                    {(a.state === "开放" ? ["截止", "已结束"] : ["已结束"]).map(
                      (s) => (
                        <Action
                          key={s}
                          run={async () => {
                            await api(
                              "/activities/" + a.id + "/state/" + s,
                              "POST",
                            );
                            await sync();
                          }}
                        >
                          {s === "已结束" ? "结束活动" : s}
                        </Action>
                      ),
                    )}
                  </div>
                )}
                {!student &&
                  a.replies?.map((r: Row) => (
                    <small key={r.id}>
                      {r.name} · {r.answer}
                    </small>
                  ))}
              </article>
            ))}
            {!acts.length && <Empty>暂无课堂活动</Empty>}
          </Panel>
        </div>
      )}
      {opened && (
        <Modal title={opened.title} close={() => M(null)}>
          <p className="pre">{opened.body}</p>
          {opened.filename && (
            <a href={"/api" + path + "/materials/" + opened.id + "/file"}>
              下载 {opened.filename}
            </a>
          )}
        </Modal>
      )}
      {withdraw && (
        <Modal title="撤回本次课堂" close={() => W(false)}>
          <p>撤回后停止接收新提交，已产生的课堂记录保留。</p>
          <Action
            run={async () => {
              await api(path + "/withdraw", "POST");
              W(false);
              Active(false);
              p.refresh();
            }}
          >
            确认撤回
          </Action>
        </Modal>
      )}
    </>
  );
}
