import { useEffect, useState } from "react";
import { api, dateText, roleNames, type Row } from "./client";
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
export function Jobs(p: PageProps) {
  const jobs = useData("/jobs", p.rev);
  return (
    <Panel title="任务记录" tools={<button onClick={p.refresh}>刷新</button>}>
      {(jobs.data || []).map((j: Row) => (
        <div className="listrow" key={j.id}>
          <span className="grow">
            <strong>
              {
                (
                  {
                    generate: "生成实验演示",
                    grade: "客观题批改",
                    export: "导出备课包",
                    analyze: "学情统计",
                  } as Row
                )[j.kind]
              }
            </strong>
            <small>
              {j.prompt || j.phase} · {dateText(j.updated)}
            </small>
            {(j.error || j.result?.reason) && (
              <small>{j.error || j.result.reason}</small>
            )}
          </span>
          <Pill v={j.state} />
          {["运行中", "排队中"].includes(j.state) && (
            <Action
              run={async () => {
                await api("/jobs/" + j.id + "/cancel", "POST");
                p.refresh();
              }}
            >
              取消
            </Action>
          )}
          {["失败", "已取消"].includes(j.state) && (
            <Action
              run={async () => {
                await api("/jobs/" + j.id + "/resume", "POST");
                p.refresh();
              }}
            >
              恢复
            </Action>
          )}
          {j.kind === "export" && j.state === "完成" && (
            <a href={"/api/jobs/" + j.id + "/file"}>下载</a>
          )}
        </div>
      ))}
      {!jobs.data?.length && <Empty>暂无后台任务</Empty>}
    </Panel>
  );
}
export function Admin(p: PageProps) {
  const isAdmin = p.user.role === "admin",
    accounts = useData(isAdmin ? "/people" : "", p.rev),
    audit = useData("/audit", p.rev),
    conf = useData(isAdmin ? "/settings" : "", p.rev);
  const [form, F] = useState<Row | null>(null),
    [cfg, C] = useState<Row>({ repair_limit: 2, timeout: 18 });
  useEffect(() => {
    if (conf.data) C(conf.data);
  }, [conf.data]);
  return (
    <div className="stack">
      {isAdmin && (
        <>
          <Panel
            title="账号与角色"
            tools={
              <button
                onClick={() =>
                  F({
                    username: "",
                    name: "",
                    password: "",
                    role: "student",
                    group_id: "物理教研组",
                    classes: "九年级一班",
                  })
                }
              >
                ＋ 新建账号
              </button>
            }
          >
            {(accounts.data || []).map((a: Row) => (
              <div className="listrow" key={a.id}>
                <span className="grow">
                  <strong>
                    {a.name} · {roleNames[a.role]}
                  </strong>
                  <small>
                    {a.username} · {a.group_id} · {a.classes.join("、")}
                  </small>
                </span>
                <Pill v={a.active ? "已启用" : "已停用"} />
                {a.id !== p.user.id && (
                  <Action
                    run={async () => {
                      await api("/people/" + a.id + "/toggle", "POST");
                      p.refresh();
                    }}
                  >
                    {a.active ? "停用" : "启用"}
                  </Action>
                )}
              </div>
            ))}
          </Panel>
          <Panel title="生成任务配置">
            <div className="toolbar">
              {[
                ["repair_limit", "修复次数上限"],
                ["timeout", "模型请求超时（秒）"],
              ].map(([k, l]) => (
                <Field label={l} key={k}>
                  <input
                    type="number"
                    value={cfg[k]}
                    onChange={(e) => C({ ...cfg, [k]: +e.target.value })}
                  />
                </Field>
              ))}
              <Action
                run={async () => {
                  await api("/settings", "PUT", cfg);
                  p.notify("已保存配置");
                }}
              >
                保存配置
              </Action>
            </div>
          </Panel>
        </>
      )}
      <Panel title="操作审计" tools={<button onClick={p.refresh}>刷新</button>}>
        {(audit.data || []).map((a: Row) => (
          <div className="record" key={a.id}>
            <b>
              {a.name}　{a.action}
            </b>
            <small>
              {dateText(a.created)} · {a.object} {a.detail}
            </small>
          </div>
        ))}
      </Panel>
      {form && (
        <Modal title="新建账号" close={() => F(null)}>
          {Object.entries({
            username: "登录名",
            name: "显示姓名",
            password: "初始密码（至少八位）",
            group_id: "教研组",
            classes: "班级（逗号分隔）",
          }).map(([k, l]) => (
            <Field label={l} key={k}>
              <input
                type={k === "password" ? "password" : "text"}
                value={form[k]}
                onChange={(e) => F({ ...form, [k]: e.target.value })}
              />
            </Field>
          ))}
          <Field label="角色">
            <select
              value={form.role}
              onChange={(e) => F({ ...form, role: e.target.value })}
            >
              {Object.entries(roleNames).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Action
            kind="primary"
            run={async () => {
              await api("/people", "POST", {
                ...form,
                classes: form.classes
                  .split(/[,，]/)
                  .map((s: string) => s.trim())
                  .filter(Boolean),
              });
              F(null);
              p.refresh();
            }}
          >
            创建账号
          </Action>
        </Modal>
      )}
    </div>
  );
}
