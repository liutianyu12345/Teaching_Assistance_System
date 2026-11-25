# 知衡物理教学工作台

面向初中物理教师和学生的教学辅助系统。仓库自带“探究电流与电压的关系”课例、三份已审核材料、一个已发布课堂和一份随堂练习。首次登录即可演示，也可以从资源草稿创建一节新课。

## 本机启动

在项目根目录运行，首次构建需要联网下载依赖。

```powershell
docker compose up --build -d
docker compose ps
```

打开 [教学工作台](http://127.0.0.1:8080) 或 [交互接口文档](http://127.0.0.1:8080/api/docs)。登录页可直接选择演示角色。普通窗口和隐私窗口分别登录教师和学生；同一浏览器配置下的标签页共享会话。退出服务用 `docker compose down`，下次启动继续使用现有数据库和附件卷。

| 演示账号 | 角色与范围 |
|---|---|
| teacher / colleague | 九年级一班教师，二人可协作编辑示范备课包 |
| lead / reviewer / admin | 物理教研组长、资源审核教师、系统管理员 |
| student1 / student2 | 九年级一班的张明、李悦 |
| student3 | 九年级二班的王晨，用于验证班级隔离 |

演示账号的密码均为 `Physics2027!`。Compose 默认只绑定本机回环网卡。创建真实教学环境时，使用新数据库，复制 `.env.example` 为 `.env`，设置 `DEMO_MODE=0`、数据库密码与至少 12 位的 `ADMIN_PASSWORD`。此模式首次只创建管理员，由其建立教师、学生和班级归属。已初始化的数据库保留原有账号与资料。

## 真实模型与离线演示

在 `.env` 设置 `MODEL_BASE_URL`、`MODEL_NAME` 和服务需要的 `MODEL_API_KEY`，然后运行 `docker compose up -d` 以更新 API 与 worker 环境。模型服务需支持在基础地址下接收 `POST /chat/completions`，返回 `choices[0].message.content` 中的配置 JSON。使用容器访问 Windows 宿主机的模型服务时，可使用 `host.docker.internal`。模型密钥仅由服务端读取。

生成工坊按组检索已发布的知识片段，保存来源、片段位置和版本。云端模型将收到教师描述与这些片段。字段与固定电阻规则由 Pydantic 校验；读数由欧姆定律计算。未配置模型、服务超时或修复耗尽时使用 10 Ω、0–6 V 的本地模板，界面显示原因。候选演示可继续对话修订，或到资源库完成审核后引用。

## 本地轻量开发

需要 Python 3.12 和 Node.js 22。以下命令从仓库根目录运行。轻量模式使用 SQLite、本地附件和线程任务执行器。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt pytest
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 [本机轻量版](http://127.0.0.1:8000)。修改前端时可以另开终端运行 `npm.cmd --prefix frontend run dev`，Vite 将 API 和 WebSocket 转发给 8000 端口。开发数据和导出文件保存在 `data/`，独立于 Compose 命名卷。测试使用自己的临时数据库。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

## 项目结构

| 目录 | 职责 |
|---|---|
| frontend/src | React 和 TypeScript 角色工作台，Three.js 电路、ECharts 曲线与学情图 |
| backend/app | FastAPI 模块、数据库建表和迁移、教学业务、LangGraph 和 Celery 任务 |
| backend/tests | 按完整教学流程验证权限、版本、计算、并发和任务恢复 |
| docs | 教学流程与数据关系、权限矩阵、答辩演示和记录方式 |

Compose 使用 PostgreSQL + pgvector、Redis、API、独立 Celery worker（含恢复扫描）和 Nginx。PostgreSQL 的章节与知识点通过资源版本和题目快照关联；知识检索采用本地 128 维字符二元组哈希向量，按余弦距离召回，用于小规模中文课例库。SQLite 使用相同向量在授权集合内计算相似度。详细操作见 [课例与验收](docs/课例与验收.md)。
