import { useState } from "react";
import { api, task, type Row } from "./client";
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

export function Lessons(p: PageProps) {
  const all = useData("/lessons", p.rev),
    sources = useData("/resources", p.rev),
    people = useData("/people", p.rev);
  const [selected, S] = useState(""),
    [dialog, D] = useState(""),
    [title, T] = useState("探究电流与电压的关系"),
    [tmpl, TM] = useState(true),
    [refs, R] = useState<string[]>([]),
    [collabs, C] = useState<string[]>([]),
    [group, G] = useState(p.user.classes[0] || ""),
    [section, Sec] = useState("目标"),
    [draft, Dr] = useState(""),
    [base, B] = useState(0),
    [conflict, CF] = useState<Row | null>(null),
    [note, N] = useState(""),
    [historic, H] = useState<Row | null>(null);
  const ls: Row | undefined =
    (all.data || []).find((x: Row) => x.id === selected) || all.data?.[0];
  const comments = useData(ls ? "/lessons/" + ls.id + "/comments" : "", p.rev),
    history = useData(ls ? "/lessons/" + ls.id + "/history" : "", p.rev);
  const writable =
      ls && (ls.owner === p.user.id || ls.collabs.includes(p.user.id)),
    owner = ls?.owner === p.user.id;
  const checked = (value: string, arr: string[], set: (x: string[]) => void) =>
    set(arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value]);
  function links(create: boolean) {
    R(create ? [] : ls!.refs);
    C(create ? [] : ls!.collabs);
    D(create ? "create" : "links");
  }
  async function saveSection() {
    try {
      await api("/lessons/" + ls!.id + "/section", "PUT", {
        section,
        text: draft,
        rev: base,
      });
      D("");
      p.refresh();
    } catch (e) {
      const d = (e as any).detail;
      if (d?.current) {
        CF(d.current);
        return;
      }
      throw e;
    }
  }
  return (
    <>
      <div className="toolbar">
        {ls && (
          <Picker items={all.data} id={ls.id} set={S} label="当前备课包" />
        )}
        <button onClick={() => links(true)} className="primary">
          ＋ 新建备课包
        </button>
        <button onClick={() => p.go("ai")}>制作 AI 演示</button>
      </div>
      <ErrorLine value={all.error} />
      {ls ? (
        <div className="two wide">
          <Panel title={ls.title} tools={<Pill v={ls.state} />}>
            <div className="meta">
              备课版本 V{ls.rev}　·　{ls.refs.length} 份引用资源　·　
              {ls.collabs.length} 位协作者
            </div>
            {Object.entries(ls.sections as Record<string, Row>).map(
              ([k, s]) => (
                <article className="sectiontext" key={k}>
                  <div>
                    <h3>{k}</h3>
                    {writable && (
                      <button
                        className="link"
                        onClick={() => {
                          Sec(k);
                          Dr(s.text);
                          B(s.rev);
                          CF(null);
                          D("edit");
                        }}
                      >
                        编辑
                      </button>
                    )}
                  </div>
                  <p>{s.text || "尚未填写"}</p>
                </article>
              ),
            )}
            <div className="actions">
              {owner && (
                <button onClick={() => links(false)}>资源与协作者</button>
              )}
              {owner && ["草稿", "协作中"].includes(ls.state) && (
                <Action
                  run={async () => {
                    await api("/lessons/" + ls.id + "/finalize", "POST", {
                      rev: ls.rev,
                    });
                    p.refresh();
                  }}
                >
                  定稿
                </Action>
              )}
              {owner && ["定稿", "已发布"].includes(ls.state) && (
                <button className="primary" onClick={() => D("publish")}>
                  发布到班级
                </button>
              )}
              {["docx", "pdf"].map((f) => (
                <Action
                  key={f}
                  run={async () => {
                    const j = await task("export", {
                      lesson: ls.id,
                      format: f,
                    });
                    window.location.assign("/api/jobs/" + j.id + "/file");
                  }}
                >
                  导出 {f === "docx" ? "Word" : "PDF"}
                </Action>
              ))}
            </div>
          </Panel>
          <div className="stack">
            <Panel title="章节批注">
              {(comments.data || []).map((n: Row) => (
                <div className="record" key={n.id}>
                  <b>
                    {n.name} · {n.section}
                  </b>
                  <p>{n.body}</p>
                </div>
              ))}
              {writable && (
                <>
                  <Field label="批注章节">
                    <select
                      value={section}
                      onChange={(e) => Sec(e.target.value)}
                    >
                      {Object.keys(ls.sections).map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </Field>
                  <textarea
                    value={note}
                    onChange={(e) => N(e.target.value)}
                    placeholder="写下讨论意见"
                  />
                  <Action
                    disabled={!note.trim()}
                    run={async () => {
                      await api("/lessons/" + ls.id + "/comments", "POST", {
                        section,
                        body: note,
                      });
                      N("");
                      p.refresh();
                    }}
                  >
                    提交批注
                  </Action>
                </>
              )}
            </Panel>
            <Panel title="版本记录">
              {(history.data || []).map((h: Row) => (
                <button
                  className="listrow"
                  key={h.id}
                  onClick={() => {
                    H(h);
                    D("history");
                  }}
                >
                  V{h.rev}
                  <strong>{h.data.state}</strong>
                  <small>查看差异</small>
                </button>
              ))}
            </Panel>
          </div>
        </div>
      ) : (
        <Empty>创建第一份备课包，从教学目标开始组织课程。</Empty>
      )}
      {(dialog === "create" || dialog === "links") && (
        <Modal
          close={() => D("")}
          title={dialog === "create" ? "新建备课包" : "资源与协作者"}
        >
          {dialog === "create" && (
            <>
              <Field label="课题">
                <input value={title} onChange={(e) => T(e.target.value)} />
              </Field>
              <label>
                <input
                  type="checkbox"
                  checked={tmpl}
                  onChange={(e) => TM(e.target.checked)}
                />{" "}
                复用电学课例模板
              </label>
            </>
          )}
          <h3>已审核资源</h3>
          {(sources.data || [])
            .filter((v: Row) => v.status === "已发布")
            .map((v: Row) => (
              <label className="check" key={v.id}>
                <input
                  type="checkbox"
                  checked={refs.includes(v.id)}
                  onChange={() => checked(v.id, refs, R)}
                />
                {v.title} · V{v.number}
              </label>
            ))}
          <h3>同组协作者</h3>
          {(people.data || [])
            .filter((u: Row) => u.id !== p.user.id)
            .map((u: Row) => (
              <label className="check" key={u.id}>
                <input
                  type="checkbox"
                  checked={collabs.includes(u.id)}
                  onChange={() => checked(u.id, collabs, C)}
                />
                {u.name}
              </label>
            ))}
          <Action
            kind="primary"
            run={async () => {
              const create = dialog === "create";
              const n = await api(
                create ? "/lessons" : "/lessons/" + ls!.id + "/links",
                create ? "POST" : "PUT",
                { title, template: tmpl, refs, collabs, rev: ls?.rev },
              );
              S(n.id);
              D("");
              p.refresh();
            }}
          >
            保存
          </Action>
        </Modal>
      )}
      {dialog === "edit" && (
        <Modal title={"编辑 · " + section} close={() => D("")}>
          <textarea
            rows={6}
            value={draft}
            onChange={(e) => Dr(e.target.value)}
          />
          {conflict && (
            <div className="note">
              <b>另一位教师已修改这一节</b>
              <p>{conflict.text}</p>
              <button
                onClick={() => {
                  B(conflict.rev);
                  CF(null);
                }}
              >
                已比较，保留我的编辑并继续
              </button>
            </div>
          )}
          <Action kind="primary" disabled={!!conflict} run={saveSection}>
            保存章节
          </Action>
        </Modal>
      )}
      {dialog === "history" && historic && ls && (
        <Modal
          title={"比较 V" + historic.rev + " 与当前版本"}
          close={() => D("")}
        >
          {Object.entries(historic.data.sections as Record<string, Row>).map(
            ([k, s]) => (
              <div className="record" key={k}>
                <b>{k}</b>
                <p>{s.text}</p>
                {s.text !== ls.sections[k].text && (
                  <small>当前 · {ls.sections[k].text}</small>
                )}
              </div>
            ),
          )}
          <p>
            引用版本 ·{" "}
            {historic.data.refs
              .map((id: string) =>
                (sources.data || []).find((x: Row) => x.id === id),
              )
              .filter(Boolean)
              .map((x: Row) => x.title + " V" + x.number)
              .join("、")}
          </p>
          {writable && (
            <Action
              run={async () => {
                await api(
                  "/lessons/" + ls.id + "/restore/" + historic.rev,
                  "POST",
                  { rev: ls.rev },
                );
                D("");
                p.refresh();
              }}
            >
              恢复为新草稿
            </Action>
          )}
        </Modal>
      )}
      {dialog === "publish" && ls && (
        <Modal title="发布课堂快照" close={() => D("")}>
          <Field label="接收班级">
            <select value={group} onChange={(e) => G(e.target.value)}>
              {p.user.classes.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Field>
          <p>学生将使用备课版本 V{ls.rev} 的资源、实验初值与可调范围。</p>
          <Action
            kind="primary"
            run={async () => {
              await api("/lessons/" + ls.id + "/publish", "POST", {
                class_id: group,
                rev: ls.rev,
              });
              D("");
              p.refresh();
              p.go("classroom");
            }}
          >
            确认发布
          </Action>
        </Modal>
      )}
    </>
  );
}
