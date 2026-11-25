import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, roleNames, type User, type Row } from "./client";
import {
  Action,
  Empty,
  ErrorLine,
  Field,
  Icon,
  Panel,
  Pill,
  useData,
  type PageProps,
} from "./widgets";
import { CircuitBoard } from "./CircuitBoard";
import { Materials, Generator } from "./Materials";
import { Lessons } from "./Lessons";
import { Classroom } from "./Classroom";
import { Practice, Analytics } from "./Practice";
import { Admin, Jobs } from "./Admin";
import "./style.css";

const pages: Record<
  string,
  {
    title: string;
    roles: string[];
    group: string;
    component: (p: PageProps) => JSX.Element;
  }
> = {
  home: {
    title: "教学总览",
    roles: ["teacher", "lead", "student", "reviewer", "admin"],
    group: "工作空间",
    component: Home,
  },
  library: {
    title: "教学资源库",
    roles: ["teacher", "lead", "reviewer", "admin"],
    group: "工作空间",
    component: Materials,
  },
  lesson: {
    title: "协作备课",
    roles: ["teacher", "lead"],
    group: "工作空间",
    component: Lessons,
  },
  classroom: {
    title: "互动课堂",
    roles: ["teacher", "lead", "student"],
    group: "工作空间",
    component: Classroom,
  },
  practice: {
    title: "练习与错题",
    roles: ["teacher", "lead", "student"],
    group: "工作空间",
    component: Practice,
  },
  chart: {
    title: "学情分析",
    roles: ["teacher", "lead"],
    group: "工作空间",
    component: Analytics,
  },
  ai: {
    title: "AI 演示工坊",
    roles: ["teacher", "lead"],
    group: "教学工具",
    component: Generator,
  },
  jobs: {
    title: "任务中心",
    roles: ["teacher", "lead", "admin", "student"],
    group: "教学工具",
    component: Jobs,
  },
  admin: {
    title: "运行管理",
    roles: ["admin", "lead", "reviewer"],
    group: "教学工具",
    component: Admin,
  },
};
function Brand() {
  return (
    <div className="brand">
      <span className="brandmark">∿</span>
      <span>
        知衡物理<small>PHYSICS STUDIO</small>
      </span>
    </div>
  );
}
function Login({ done }: { done: (u: User) => void }) {
  const demo = useData("/demo"),
    [name, N] = useState(""),
    [pass, P] = useState(""),
    [error, E] = useState("");
  async function login(user: string, password: string) {
    try {
      E("");
      done(await api("/login", "POST", { username: user, password }));
    } catch (e) {
      E((e as Error).message);
    }
  }
  return (
    <div className="login">
      <div className="loginart">
        <Brand />
        <div className="loginscene">
          <span className="unit">九年级物理　/　电学实验</span>
          <h1>
            探究电流与
            <br />
            电压的关系
          </h1>
          <CircuitBoard voltage={3} />
          <p>定值电阻实验　·　控制变量法</p>
        </div>
      </div>
      <main className="loginform">
        <div>
          <h1>登录教学工作台</h1>
          <p>使用教学账号进入你的工作空间。</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void login(name, pass);
            }}
          >
            <Field label="账号">
              <input
                autoComplete="username"
                required
                value={name}
                onChange={(e) => N(e.target.value)}
              />
            </Field>
            <Field label="密码">
              <input
                type="password"
                autoComplete="current-password"
                required
                value={pass}
                onChange={(e) => P(e.target.value)}
              />
            </Field>
            <ErrorLine value={error || demo.error} />
            <button className="primary">登录</button>
          </form>
          {demo.data?.enabled && (
            <>
              <h3>课例演示账号</h3>
              <div className="demochoices">
                {[
                  ["teacher", "林老师 · 教师"],
                  ["student1", "张明 · 学生"],
                  ["student2", "李悦 · 学生"],
                  ["colleague", "陈老师 · 协作"],
                  ["reviewer", "审核教师"],
                  ["admin", "管理员"],
                ].map(([id, s]) => (
                  <Action key={id} run={() => login(id, "Physics2027!")}>
                    {s}
                  </Action>
                ))}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
function Home(p: PageProps) {
  const staff = ["teacher", "lead"].includes(p.user.role),
    student = p.user.role === "student";
  const rooms = useData(staff || student ? "/classrooms" : "", p.rev),
    materials = useData(!student ? "/resources" : "", p.rev),
    lessons = useData(staff ? "/lessons" : "", p.rev),
    jobs = useData(p.user.role !== "reviewer" ? "/jobs" : "", p.rev);
  const room = rooms.data?.[0],
    c = room?.snapshot.config;
  const shortcuts = staff
    ? [
        ["library", "教学资源", "检索与审核课例材料"],
        ["lesson", "协作备课", "组织教学内容与资源"],
        ["ai", "生成演示", "设计可调节的物理实验"],
      ]
    : student
      ? [
          ["classroom", "进入课堂", "调节电压与记录观察"],
          ["practice", "练习与错题", "作答与复习错题"],
          ["jobs", "任务记录", "查看批改进度"],
        ]
      : [
          ["library", "资源审核", "查阅待审核版本"],
          ["admin", "运行管理", "查看操作记录"],
        ];
  const stats = student
    ? [
        ["分配课堂", rooms.data?.length, "classroom"],
        [
          "开放课堂",
          rooms.data?.filter((r: Row) => r.active).length,
          "classroom",
        ],
        ["我的任务", jobs.data?.length, "jobs"],
      ]
    : [
        ["资源版本", materials.data?.length, "library"],
        [
          "待审核",
          materials.data?.filter((x: Row) => x.status === "待审核").length,
          "library",
        ],
        staff
          ? ["备课包", lessons.data?.length, "lesson"]
          : [
              "已发布资源",
              materials.data?.filter((x: Row) => x.status === "已发布").length,
              "library",
            ],
      ];
  return (
    <>
      <div className="homehead">
        <div>
          <span className="eyebrow">
            {p.user.group_id}　/　{roleNames[p.user.role]}
          </span>
          <h1>{p.user.name}，你好</h1>
        </div>
        <div className="date">
          {new Date().toLocaleDateString("zh-CN", {
            month: "long",
            day: "numeric",
            weekday: "long",
          })}
        </div>
      </div>
      {(staff || student) && room && (
        <div className="hero">
          <div>
            <span className="unit">
              <i /> {room.class_id}　·　电学探究
            </span>
            <h2>{room.snapshot.title}</h2>
            <p>保持电阻不变，调节电压并记录电流，观察伏安曲线。</p>
            <button onClick={() => p.go("classroom")}>
              进入实验课堂 <Icon name="arrow" size={16} />
            </button>
          </div>
          <CircuitBoard resistance={c.resistance} voltage={c.initial} />
        </div>
      )}
      <div className="stats">
        {stats.map(([s, n, k]) => (
          <button key={s} onClick={() => p.go(k)}>
            <span className="statIcon">
              <Icon name={k} />
            </span>
            <span>
              <small>{s}</small>
              <strong>{n ?? "—"}</strong>
            </span>
            <span className="statArrow">↗</span>
          </button>
        ))}
      </div>
      <div className="homegrid">
        <Panel
          title={student ? "我的课堂" : "教学资源"}
          tools={
            <button
              className="link"
              onClick={() => p.go(student ? "classroom" : "library")}
            >
              查看全部 →
            </button>
          }
        >
          {(student ? rooms.data : materials.data)
            ?.slice(0, 4)
            .map((x: Row, i: number) => (
              <button
                className="listrow"
                key={x.id}
                onClick={() => p.go(student ? "classroom" : "library")}
              >
                <span className={"tile t" + i}>
                  <Icon
                    name={student ? "classroom" : x.config ? "bolt" : "book"}
                  />
                </span>
                <span className="grow">
                  <strong>{x.title || x.snapshot.title}</strong>
                  <small>
                    {x.kind || x.class_id} · {x.point || "课例快照"}
                  </small>
                </span>
                <Pill v={x.status || (x.active ? "已发布" : "已撤回")} />
              </button>
            ))}
          {(student ? rooms.data : materials.data)?.length === 0 && (
            <Empty>暂无记录</Empty>
          )}
        </Panel>
        <Panel title="快捷操作">
          {shortcuts.map(([id, s, desc]) => (
            <button className="quick" key={id} onClick={() => p.go(id)}>
              <Icon name={id} />
              <span className="grow">
                <strong>{s}</strong>
                <small>{desc}</small>
              </span>
              <span>↗</span>
            </button>
          ))}
        </Panel>
      </div>
    </>
  );
}
function App() {
  const [user, U] = useState<User | null>(null),
    [ready, R] = useState(false),
    [page, S] = useState(location.hash.slice(1) || "home"),
    [rev, V] = useState(0),
    [notice, N] = useState(""),
    [menu, M] = useState(false);
  useEffect(() => {
    api("/me")
      .then(U)
      .catch(() => {})
      .finally(() => R(true));
    const navigate = () => S(location.hash.slice(1) || "home"),
      toast = (e: Event) => N((e as CustomEvent).detail),
      expired = () => U(null);
    window.addEventListener("hashchange", navigate);
    window.addEventListener("notice", toast);
    window.addEventListener("session-expired", expired);
    return () => {
      window.removeEventListener("hashchange", navigate);
      window.removeEventListener("notice", toast);
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => N(""), 4800);
      return () => clearTimeout(t);
    }
  }, [notice]);
  function go(s: string) {
    location.hash = s;
    S(s);
    M(false);
    window.scrollTo({ top: 0 });
  }
  if (!ready) return <div className="loading">正在打开教学工作台…</div>;
  if (!user)
    return (
      <Login
        done={(u) => {
          U(u);
          go("home");
        }}
      />
    );
  const allowed = Object.entries(pages).filter(([, v]) =>
      v.roles.includes(user.role),
    ),
    key = allowed.some(([k]) => k === page) ? page : "home",
    Page = pages[key].component;
  return (
    <div className="shell">
      <aside className={menu ? "shown" : ""}>
        <Brand />
        <nav>
          {["工作空间", "教学工具"].map((g) => (
            <div key={g}>
              <small>{g}</small>
              {allowed
                .filter(([, v]) => v.group === g)
                .map(([k, item]) => (
                  <button
                    className={k === key ? "active" : ""}
                    key={k}
                    onClick={() => go(k)}
                  >
                    <Icon name={k} />
                    {item.title}
                  </button>
                ))}
            </div>
          ))}
        </nav>
        <div className="profile">
          <span className="avatar">{user.name[0]}</span>
          <div className="grow">
            <strong>{user.name}</strong>
            <small>{roleNames[user.role]}</small>
          </div>
          <Action
            kind="iconbtn"
            run={async () => {
              await api("/logout", "POST");
              U(null);
              M(false);
              go("home");
            }}
          >
            <span title="退出登录">
              <Icon name="exit" size={17} />
            </span>
          </Action>
        </div>
      </aside>
      {menu && <div className="scrim" onClick={() => M(false)} />}
      <main className="workspace">
        <header className="top">
          <button className="mobile" onClick={() => M(!menu)}>
            菜单
          </button>
          <span>
            教学工作台　<span>／</span>　<b>{pages[key].title}</b>
          </span>
          <span className="subject">
            <i /> 初中物理
          </span>
        </header>
        <div className="content">
          {key !== "home" && <h1 className="pagetitle">{pages[key].title}</h1>}
          <Page
            key={user.id + key}
            user={user}
            rev={rev}
            refresh={() => V((x) => x + 1)}
            go={go}
            notify={N}
          />
        </div>
      </main>
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button onClick={() => N("")}>×</button>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
