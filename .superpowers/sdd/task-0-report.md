# Task 0: 项目骨架与基础设施 — 实施报告

## 1. 实施内容

创建了 停顿标注工具 (Pause Annotation Tool) 的完整项目骨架，包含以下文件：

### 基础设施
- `.env.example` — 环境变量模板
- `requirements.txt` — Python 依赖 (追加 `itsdangerous`)
- `data/.gitkeep` — 数据目录占位

### Python 包 (app/)
- `app/__init__.py` — 包标识
- `app/config.py` — 配置管理 (pydantic-settings)
- `app/database.py` — 异步数据库引擎 + WAL 模式
- `app/models.py` — 6 个 ORM 模型 (Experimenter, Session, Utterance, AnnotationTarget, Annotation, GlobalSetting)
- `app/schemas.py` — Pydantic 请求/响应模型
- `app/auth.py` — Pipeline Token 验证 + 管理员认证
- `app/utils.py` — 工具函数 (token生成, easyturn解析, 默认配置)
- `app/main.py` — FastAPI 应用入口 (含健康检查端点、生命周期管理)
- `app/routers/__init__.py` — 路由包标识
- `app/routers/pipeline.py` — Pipeline 路由占位
- `app/routers/participant.py` — 参与者路由占位
- `app/routers/admin.py` — 管理路由占位

### 脚本 & 静态文件
- `scripts/install.sh` — 安装脚本
- `scripts/run.sh` — 运行脚本
- `static/index.html` — 前端入口
- `static/css/style.css` — 前端样式

## 2. 测试结果

健康检查端点通过验证：
```
$ curl http://127.0.0.1:8000/api/health
{"status":"ok"}
```

静态文件服务正常:
- `/` → index.html ✓
- `/css/style.css` → CSS ✓

## 3. 创建文件数

18 个文件

## 4. 注意事项

- **Starlette 路由优先级**：`app.mount("/", StaticFiles(...))` 必须在所有 `app.get()` 和 `app.include_router()` 之后注册，否则 Mount 会捕获所有请求（包括 API 路由），因为 `/` 路径前缀匹配一切。已在 `main.py` 中将静态文件挂载移至文件末尾。
- **依赖**：`itsdangerous` 是 `starlette.middleware.sessions.SessionMiddleware` 的隐式依赖，已追加到 `requirements.txt`。

## 5. 返回状态

DONE

## 6. Commits

1. `bb6508f` — feat: initialize project skeleton with FastAPI backend
   - 21 files created, 580 insertions
   - Created all app modules, models, schemas, auth, utils
   - Set up FastAPI with lifespan, CORS, session middleware
   - Added static file serving, scripts, and configuration

2. `81a75d4` — docs: update task-0 report with commit hash

3. `09842f5` — docs: fix commit hash in task-0 report
