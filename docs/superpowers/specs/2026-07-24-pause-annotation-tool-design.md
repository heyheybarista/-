# 口语停顿回溯标注工具 — 产品设计文档

- **日期**：2026-07-24
- **状态**：已确认（2026-07-24）；项目根目录：`停顿标注工具/`
- **范围**：预实验可用的 Web 产品；与 EasyTurn / VAD 流水线对接；支持线上/线下主试与远程被试

---

## 1. 背景与目标

### 1.1 实验流程中的位置

被试与主试完成英语口语表达任务时：

1. 实时转录主试与被试语音；
2. 音频流经 VAD 处理后，被试侧送入 EasyTurn 话轮模型，得到句级标签（及后续可接停顿时长）；
3. **任务结束后**，被试需对表达过程中的「停顿 / 未完成 / 等待」等标记，回溯填写原因与心理过程，并报告确信度。

本产品覆盖第 3 步：**呈现完整转录 + EasyTurn 标记 → 被试填写 → 数据回到主试端**。

### 1.2 产品目标

| 目标 | 说明 |
|------|------|
| 呈现 | 完整对话（主试 + 被试）与被试侧 EasyTurn 标记 |
| 填写 | 每个需标注点：原因类别（必选）+ 开放描述 + 1–7 置信度 |
| 远程 | 线上被试通过一次性私密链接填写，无需登录 |
| 回收 | 数据保存在部署主机，主试可查看进度并导出 |
| 可配置 | 指导语、可标注标签、原因类别可由管理员修改 |
| 可对接 | Python 流水线通过 HTTP 自动创建会话 |
| 可迁移 | 可打包部署到「VAD + EasyTurn」主机，不绑开发机 |

### 1.3 非目标（第一版明确不做）

- 音频回放 / 波形
- 句内多段精细声学 pause 编辑（接口预留时长字段）
- 会话级主试数据强隔离
- 邮件 / 微信自动发送被试链接
- 复杂多租户、多实验权限体系
- 被试账号体系

---

## 2. 角色与端到端流程

### 2.1 角色

| 角色 | 职责 |
|------|------|
| 流水线服务 | 任务结束推送会话；获取被试链接 |
| 主试（experimenter） | 查看全部会话、复制链接、看进度、导出、重置提交 |
| 管理员（admin） | 上述 + 指导语 / 标签 / 类别 / 主试账号管理 |
| 被试 | 打开私密链接，填写全部标注点后提交 |

### 2.2 主流程

```text
[口语任务]
  音频流 → VAD → ASR（双方）
  → 被试侧 EasyTurn → 句级标签
  →（后续）停顿/状态相关时长

[任务结束]
  流水线 POST /api/pipeline/sessions
  → 系统创建 Session + AnnotationTarget
  → 返回 participant_url
  → 主试复制链接发给被试

[被试填写]
  打开 /a/{token}
  → 阅读指导语
  → 在完整对话中对需标注点：类别 + 描述 + 置信度
  → 自动暂存
  → 全部完成后提交 → 锁定只读

[主试回收]
  列表 / 详情 / 导出 JSON·CSV
```

### 2.3 会话状态机

```text
created →（被试首次打开）→ in_progress →（全部填完并提交）→ submitted
                                      ↑                         │
                                      └──── 主试重置（默认清空标注）┘
```

零标注点会话：允许创建；界面显示「无需标注」；可提供「确认完成」或主试侧标记处理完毕。

---

## 3. 功能设计

### 3.1 被试填写页（`/a/{token}`）

**布局**

1. **顶栏**：标题、进度（已完成/总数）、自动保存状态、提交按钮（未完成时禁用）
2. **中央指导语卡片**：可折叠；首次默认展开；内容来自指导语快照
3. **对话流**：按时间顺序；主试 / 被试样式区分；仅「需标注」的被试句展开表单

**每个标注点字段**

| 字段 | 规则 |
|------|------|
| 原因类别 | 必选；选项来自全局类别配置 |
| 原因与心理过程 | 必填文本；颗粒度/字数建议写在指导语，不在表单项堆长说明 |
| 置信度 | 必选 1–7；文案：「你在多大程度上确信该停顿原因的描述？1=完全不确信，7=完全确信」 |

**交互**

- 自动暂存：类别变更、描述防抖约 1s、置信度点选 → PATCH
- 提交前二次确认；服务端校验全部 required 目标已 complete
- 提交后只读；同一链接可再次打开查看
- 适配手机竖屏（线上被试）

**标签展示策略**

| EasyTurn 标签 | 默认徽章文案 | 默认是否需填写 |
|---------------|--------------|----------------|
| incomplete | 未说完 | 是 |
| wait | 等待 | 是 |
| complete | 完整 | 否（可配置） |
| backchannel | 附和 | 否（可配置） |

第一版标注粒度：**一句 utterance ≤ 一个 annotation target**（与 EasyTurn 句级输出一致）。

### 3.2 默认原因类别（admin 可改）

| value | 显示名 |
|-------|--------|
| lexical | 找词 / 词汇提取 |
| syntax | 句法 / 句子组织 |
| thinking | 内容思考 |
| intention_shift | 意图切换 |
| interactive | 互动 / 等待对方 |
| external | 外部干扰 |
| other | 其他 |

### 3.3 默认指导语（admin 可改）

> **任务说明**  
> 下面呈现的是你刚才与主试完成英语口语任务时的对话转录。系统已在你的部分发言处标出可能与「未说完 / 需要等待」相关的位置（由话轮模型自动标记）。  
>
> **请你做什么**  
> 请依次查看每一处标记。结合前后对话，回忆当时你为什么会这样停顿、犹豫或没有继续说完，并填写：  
> 1）最符合的原因类别；  
> 2）当时的原因与心理过程（请写具体一些，例如你在想哪个词、哪句结构、还是在组织内容）；  
> 3）你对上述描述的确信程度（1–7）。  
>
> **描述建议**  
> - 请尽量描述「当下」的想法，而不是事后合理化。  
> - 建议每处约 20–100 字；若确实记不清，可如实写“记不清”，并在置信度上选择较低分数。  
> - 主试的发言仅帮助你回忆语境，无需对主试发言作答。  
>
> **提交**  
> 所有标记处填写完成后，点击顶部「提交」。提交后不可再修改。填写过程中会自动保存进度，可中途关闭，稍后用同一链接继续。

**快照策略**：会话创建时（或被试首次打开时）固化 `instruction_snapshot`，避免事后改指导语污染已提交数据的解释。

### 3.4 主试端（多账号，B1 全可见）

**路由**

| 路径 | 功能 |
|------|------|
| `/admin/login` | 用户名 + 密码登录 |
| `/admin/sessions` | 会话列表：编号、时间、状态、进度、操作 |
| `/admin/sessions/:id` | 详情：复制链接、预览标注、重置、导出本场 |
| `/admin/settings` | 指导语、可标注标签、原因类别（admin） |
| `/admin/users` | 主试账号增删 / 重置密码（admin） |

**权限**

| 能力 | experimenter | admin |
|------|---------------|-------|
| 查看全部会话 | ✓ | ✓ |
| 复制链接 / 导出 / 重置 | ✓ | ✓ |
| 改指导语 / 标签 / 类别 | | ✓ |
| 管理主试账号 | | ✓ |

不按主试隔离会话（B1）。链接由主试人工分发，系统不自动通知。

---

## 4. 数据模型

### 4.1 实体关系

```text
Session
├── Utterance[]  （主试 + 被试，按 seq 排序）
│   └── AnnotationTarget?  （被试 + 标签∈可标注集合时生成）
│       └── Annotation?
├── instruction_snapshot
└── meta（被试外部编号、pipeline_meta 等）

Experimenter（主试账号）
Settings（全局键值配置）
```

### 4.2 主要字段

**sessions**：`id`, `external_participant_id`, `title`, `status`, `access_token`, `created_at`, `opened_at`, `submitted_at`, `pipeline_meta`, `instruction_snapshot`, `annotatable_labels`

**utterances**：`id`, `session_id`, `seq`, `speaker` (`participant`|`experimenter`), `text`, `raw_text`, `easyturn_label`, `start_ms`, `end_ms`, `duration_ms`, `extra`

**annotation_targets**：`id`, `session_id`, `utterance_id`, `label`, `required`, `display_hint`, `pause_duration_ms`（预留）

**annotations**：`id`, `target_id`（unique）, `category`, `description`, `confidence` (1–7), `updated_at`, `is_complete`

**experimenters**：`id`, `username`, `password_hash`, `role` (`admin`|`experimenter`), `is_active`, `created_at`

**settings**：指导语、默认可标注标签、原因类别列表等

### 4.3 EasyTurn 解析规则

样例原始输出：

```text
因为小时候<incomplete><|endoftext|>
```

规范化：

1. 去除 `<|endoftext|>` 等特殊符；
2. 提取尾部标签 `<wait|complete|incomplete|backchannel>`；
3. `easyturn_label` = 小写标签名；
4. `text` = 去标签后的转写；
5. `raw_text` = 保留清洗后的原串。

建议流水线侧先规范化再推送；服务端再做一次兜底解析。

---

## 5. API 契约

### 5.1 流水线：创建会话

`POST /api/pipeline/sessions`  
Header: `Authorization: Bearer <PIPELINE_TOKEN>`

```json
{
  "external_participant_id": "P017",
  "title": "预实验-口语任务",
  "annotatable_labels": ["incomplete", "wait"],
  "pipeline_meta": {
    "easyturn_model": "Easy-Turn/checkpoint.pt",
    "asr": "whisper-xxx"
  },
  "utterances": [
    {
      "seq": 1,
      "speaker": "experimenter",
      "text": "你有没有发生过一些童年趣事呀",
      "raw_text": "你有没有发生过一些童年趣事呀<complete>",
      "easyturn_label": "complete",
      "start_ms": 1200,
      "end_ms": 4200
    },
    {
      "seq": 2,
      "speaker": "participant",
      "text": "因为小时候",
      "raw_text": "因为小时候<incomplete>",
      "easyturn_label": "incomplete",
      "start_ms": 4500,
      "end_ms": 6200,
      "pause_duration_ms": 800
    }
  ]
}
```

响应：

```json
{
  "session_id": "…",
  "access_token": "…",
  "participant_url": "http://<PUBLIC_BASE_URL主机端口>/a/…",
  "admin_url": "http://<PUBLIC_BASE_URL主机端口>/admin/sessions/…",
  "target_count": 1,
  "status": "created"
}
```

同机流水线示例：`POST http://127.0.0.1:8000/api/pipeline/sessions`。  
交付物包含简短 `pipeline_client.py` 示例。

### 5.2 被试 API（token）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/a/{token}` | 会话 + 话语 + targets + 草稿 + 指导语 |
| PATCH | `/api/a/{token}/annotations/{target_id}` | 暂存 |
| POST | `/api/a/{token}/submit` | 全量校验后提交 |

### 5.3 主试 API（登录 session）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/login` | 登录 |
| POST | `/api/admin/logout` | 登出 |
| GET | `/api/admin/sessions` | 列表 |
| GET | `/api/admin/sessions/{id}` | 详情 |
| POST | `/api/admin/sessions/{id}/reset` | 重置 |
| GET | `/api/admin/sessions/{id}/export?format=json\|csv` | 导出 |
| GET/PUT | `/api/admin/settings` | 设置（admin） |
| CRUD | `/api/admin/users` | 主试账号（admin） |

### 5.4 导出

- **JSON**：整场结构，含 instruction_snapshot 与每条 annotation
- **CSV**：一行一个 annotation target（session_id、被试编号、seq、text、label、category、description、confidence、时长等）

### 5.5 扩展预留（VAD 时长 / 多 pause）

已预留：`start_ms`, `end_ms`, `duration_ms`, `pause_duration_ms`, `pipeline_meta`。  
有 `pause_duration_ms` 时可在标记条展示「约 x.x s」。  
未来一句多 pause：改为 utterance 1—N targets，填写 UI 按列表渲染。

---

## 6. 技术架构

### 6.1 选型

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / FastAPI |
| 数据库 | SQLite（SQLAlchemy，WAL） |
| 前端 | 轻量 Web（Vite + Vue 3 或等价） |
| 进程 | uvicorn + systemd（或 Docker） |
| 反代 | Nginx（建议，承载 HTTPS） |

### 6.2 架构示意

```text
线上/线下主试  ──┐
线上/线下被试  ──┼──► 公网 HTTP 端口 ──► FastAPI/uvicorn
同机流水线     ──┘   （可选 Nginx 反代，非必须）
                           ├─ SQLite (data/app.db)
                           └─ 静态前端
```

### 6.3 鉴权分离

| 调用方 | 方式 |
|--------|------|
| 流水线 | Bearer `PIPELINE_TOKEN` |
| 主试 | 用户名密码 → HTTP-only session cookie |
| 被试 | URL 中高熵 `access_token` |

---

## 7. 部署与打包

### 7.1 部署目标

- **运行主机** = 负责 VAD 与 EasyTurn 的机器（可与开发机分离）
- **硬前提（本实验）**：线上被试必须能**不连 VPN、从公网直接打开**填写链接  
  → 目标机必须具备公网可达路径（公网 IP 或合规的端口映射等）
- **传输协议（已定）**：**公网 HTTP 即可**，第一版不强制 HTTPS  
  - 示例：`PUBLIC_BASE_URL=http://<公网IP>:<端口>`  
  - 后续若具备域名与证书，可再升级为 HTTPS，无需改业务代码

### 7.2 交付形态

| 优先级 | 形态 |
|--------|------|
| 必做 | 可迁移项目包 + `requirements`/`pyproject` + `.env.example` + install/run 脚本 + 部署说明 +（可选）systemd 单元 |
| 可选 | Docker / docker-compose（数据卷挂载 `data/`） |

换机步骤概念：

1. 拷贝或 git 拉取项目到目标机  
2. 配置 `.env`（尤其 `PUBLIC_BASE_URL`、`PIPELINE_TOKEN`、`SECRET_KEY`）  
3. 安装依赖并启动  
4. （可选）Nginx 反代；第一版也可直接暴露应用端口  
5. 用手机 4G 网络打开被试测试链接做验收  

### 7.3 关键环境变量

```text
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=http://<公网IP>:<端口>
PIPELINE_TOKEN=...
SECRET_KEY=...
DATABASE_PATH=./data/app.db
```

`participant_url` 一律基于 `PUBLIC_BASE_URL` 生成，避免出现只有内网可打开的链接。

### 7.4 网络说明

| 条件 | 线上被试远程填写 |
|------|------------------|
| 仅内网、无映射/穿透 | 不可用 |
| 仅校园网 + 需 VPN | 不符合本实验「必须公网直开」要求 |
| **公网 HTTP** | **本项目采用方案：可用** |
| 公网 HTTPS | 可选升级，非第一版要求 |

**硬条件是公网可达；协议采用 HTTP。** 链接中的 `access_token` 仍依赖高熵与不公开传播；勿在公开群传播完整填写链接。

### 7.5 部署验收清单

1. 本机 `curl` API 健康检查通过  
2. 同机流水线 `POST` 可创建会话  
3. 至少 2 个主试账号可登录且均可见该会话  
4. **手机蜂窝网络**打开 `http://...` 的 `participant_url` 可加载填写页  
5. 暂存、提交、导出链路跑通  
6. `data/app.db` 备份脚本可执行  

---

## 8. 安全

- 主试密码哈希存储（bcrypt/argon2）  
- 被试 token 高熵、不可枚举  
- 流水线 token 与主试账号分离  
- 提交后只读；重置需登录 + 二次确认  
- 公网 HTTP 部署；限制仅开放必要端口；token 高熵、链接不公开传播  
- 架构保留日后升级 HTTPS 的空间（改 `PUBLIC_BASE_URL` + 反代即可）  
- 定期备份 SQLite  
- 记录关键操作日志（登录、重置、改设置）  

---

## 9. 实施分期

### 第 0 期：环境与骨架

- 项目骨架、配置、SQLite、健康检查  
- 目标机安装方式验证  

### 第 1 期：被试 MVP

- 创建会话 API（含模拟数据）  
- 填写页：对话流、标注表单、自动暂存、提交锁定  
- 默认指导语 / 类别 / 标签  

### 第 2 期：主试端

- 多主试登录（B1）  
- 会话列表/详情、复制链接、进度、导出、重置  
- admin：指导语、标签、类别、账号管理  

### 第 3 期：真流水线与预实验打磨

- EasyTurn 输出对接与解析兜底  
- 时长字段可选展示  
- 公网 HTTP 部署验收（手机 4G 打开链接）  
- 移动端与错误提示打磨  
- 1–2 场冒烟实验  

### 延后

- 音频回放、句内多 pause、会话隔离、自动通知  

---

## 10. 成功标准

1. 流水线（或同机客户端）创建会话后，后台出现正确 `target_count`  
2. 被试公网打开私密链接可填；刷新不丢草稿  
3. 未全填不能提交；提交后只读  
4. ≥2 主试账号均可登录、见同一会话、复制链接、导出  
5. 导出含被试编号、seq、text、label、category、description、confidence  
6. admin 可改指导语；已提交会话保留 snapshot  
7. 产品可打包迁移到 VAD/EasyTurn 主机，并完成**公网 HTTP**验收  

---

## 11. 风险与对策

| 风险 | 对策 |
|------|------|
| 目标机无公网 | 部署前确认公网 IP/端口映射；否则线上被试不可用 |
| EasyTurn 格式变化 | raw 留存 + 服务端正则兜底 |
| 零标注点 | 允许创建并明确 UI 状态 |
| SQLite 并发 | WAL；预实验写入量小；必要时迁 Postgres |
| 主试误重置 | 二次确认 + 操作日志 |
| 链接泄露 | 高熵 token；仅主试端展示；勿公开群发无必要信息 |

---

## 12. 决策记录（摘要）

| 议题 | 决策 |
|------|------|
| 架构 | FastAPI + 轻量 Web + SQLite |
| 数据进入 | 流水线自动建会话（方案 B） |
| 会话范围 | 整场一份，统一提交 |
| 填写结构 | 类别 + 描述 + 1–7 置信度 |
| 标记来源 | EasyTurn 句级标签；默认可填 incomplete/wait；可配置 |
| 呈现 | 完整对话；仅被试可填 |
| 音频 | 第一版不做 |
| 保存 | 自动暂存；提交锁定 |
| 主试端 | 标准档 + 多账号 B1 全可见 |
| 链接分发 | 主试复制发送 |
| 部署机 | VAD/EasyTurn 主机；可打包迁移 |
| 线上被试 | 必须公网直开；**采用 HTTP**（HTTPS 可选升级） |
| 交付 | 项目包+脚本必做；Docker 可选 |

---

## 13. 下一步

用户审阅本设计文档并确认无修改后，进入 **implementation plan**（`writing-plans`）：按第 0–3 期拆解可执行任务、目录结构、接口明细与验收步骤。
