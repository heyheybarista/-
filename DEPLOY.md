# Render 部署指南

## 准备工作

✅ 你已经完成：将项目上传到 GitHub

## 部署步骤

### 1. 注册 Render 账号

访问 [https://render.com](https://render.com)，使用 GitHub 账号登录（推荐）

### 2. 创建新的 Web Service

1. 登录后点击右上角 **「New +」** → 选择 **「Web Service」**
2. 点击 **「Connect a repository」**，授权 Render 访问你的 GitHub
3. 找到你的项目仓库，点击 **「Connect」**

### 3. 配置部署参数

Render 会自动检测到 `render.yaml` 配置文件。如果使用 Blueprint：

- 点击 **「Apply」** 使用 `render.yaml` 中的配置

如果手动配置，填写以下信息：

| 字段 | 值 |
|------|-----|
| **Name** | `pause-annotation-tool`（或任意名称） |
| **Region** | 选择 **Singapore** 或 **Oregon**（离中国较近） |
| **Branch** | `master` 或 `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | 选择 **Free**（免费层）|

### 4. 配置环境变量（手动配置时需要）

在 **Environment Variables** 部分添加：

| Key | Value |
|-----|-------|
| `HOST` | `0.0.0.0` |
| `PUBLIC_BASE_URL` | 留空（部署后自动填写）|
| `PIPELINE_TOKEN` | 生成一个随机字符串（至少32位） |
| `SECRET_KEY` | 生成另一个随机字符串（至少32位） |
| `DATABASE_PATH` | `/data/app.db` |

**生成随机密钥的方法：**

```bash
# 在本地 Git Bash 或 Linux 终端运行
openssl rand -hex 32
```

或在 Python 中：
```python
import secrets
print(secrets.token_urlsafe(32))
```

### 5. 添加持久化存储（重要！）

Render 免费层**不包含持久化磁盘**，需要升级到付费计划或使用其他方案：

**方案 A：升级到 Starter 计划（$7/月）**
- 在 Service 设置中添加 **Disk**
- Name: `pause-annotation-data`
- Mount Path: `/data`
- Size: `1 GB`

**方案 B：使用外部数据库（推荐用于生产）**
- 改用 PostgreSQL（Render 提供免费 PostgreSQL）
- 需要修改代码，将 SQLite 改为 PostgreSQL

**方案 C：接受数据丢失（仅测试用）**
- 每次服务重启数据会丢失
- 适合快速测试，不适合正式收集数据

### 6. 部署

1. 点击 **「Create Web Service」**
2. Render 会自动：
   - 克隆你的 GitHub 仓库
   - 安装依赖
   - 启动服务
3. 等待 3-5 分钟，状态变为 **「Live」**

### 7. 获取公网地址

部署成功后，Render 会给你一个地址，格式如：

```
https://pause-annotation-tool.onrender.com
```

### 8. 更新 PUBLIC_BASE_URL

**重要！** 部署完成后：

1. 进入 Service 的 **「Environment」** 标签
2. 找到 `PUBLIC_BASE_URL`，填入你的 Render 地址（如上面的地址）
3. 点击 **「Save Changes」**
4. 服务会自动重启

### 9. 验证部署

访问以下地址测试：

- 健康检查：`https://你的地址.onrender.com/api/health`
- 主试登录：`https://你的地址.onrender.com/admin-login.html`

默认账号：
- 用户名：`admin`
- 密码：`admin`

**登录后立即修改密码！**

### 10. 后续更新

每次你推送代码到 GitHub，Render 会自动重新部署。

手动触发部署：
- 在 Render Dashboard → 点击 **「Manual Deploy」** → **「Deploy latest commit」**

---

## 免费层限制

Render 免费层限制：

| 限制项 | 说明 |
|--------|------|
| **自动休眠** | 15分钟无请求后休眠，下次访问需等待 50 秒冷启动 |
| **运行时长** | 每月 750 小时（约 31 天，足够单个服务） |
| **无持久化磁盘** | 数据库文件会在服务重启后丢失 |
| **带宽** | 100 GB/月 |

**建议：**
- 测试阶段使用免费层
- 正式收集数据时升级到 Starter（$7/月）获得持久化磁盘

---

## 常见问题

### Q1：服务打开很慢？

A：免费层会在 15 分钟无活动后休眠，首次访问需要 50 秒唤醒。可以：
- 升级到付费计划（不休眠）
- 或使用定时任务每 10 分钟访问一次健康检查接口保持活跃

### Q2：数据丢失了？

A：免费层没有持久化存储，服务重启会丢失数据。解决方案：
- 升级到 Starter 添加 Disk
- 或改用 PostgreSQL

### Q3：被试端链接打不开？

A：检查 `PUBLIC_BASE_URL` 是否正确设置为 Render 给你的地址（以 `https://` 开头）

### Q4：想用自己的域名？

A：Render 支持自定义域名：
- 进入 Service → Settings → Custom Domain
- 添加你的域名并按提示配置 DNS

---

## 推送更新到 GitHub

在项目目录下运行：

```bash
# 添加新创建的文件
git add render.yaml build.sh DEPLOY.md .gitignore

# 提交
git commit -m "feat: add Render deployment configuration"

# 推送到 GitHub
git push origin master  # 如果你的分支是 main，用 git push origin main
```

推送后，Render 会自动检测到变化并重新部署。

---

## 需要帮助？

- Render 文档：https://render.com/docs
- 项目 README：[README.md](README.md)
