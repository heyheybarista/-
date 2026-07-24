# 口语停顿回溯标注工具

## 简介

英语口语任务结束后，为被试提供对话转录与 EasyTurn 停顿标记的回溯标注页面。
被试远程填写每个停顿点的原因类别、心理过程描述与置信度（1–7）。
主试通过后台查看进度、分发链接、导出数据。

## 部署环境要求

- Python ≥ 3.11
- 目标主机必须有**公网可达**的 IP（线上被试需直接打开链接）

## 快速开始

### 1. 安装

```bash
cd 停顿标注工具
bash scripts/install.sh
```

### 2. 配置

编辑 `.env`，至少修改以下三项：

```text
PUBLIC_BASE_URL=http://<你的公网IP>:8000
PIPELINE_TOKEN=<随机长密钥>
SECRET_KEY=<随机长密钥>
```

### 3. 启动

```bash
bash scripts/run.sh
```

### 4. 初始化管理员

首次启动后，默认管理员账号：`admin` / `admin`。
登录后请立即修改密码。

### 5. 流水线对接

口语任务结束后调用：

```bash
python scripts/pipeline_client.py \
  --base-url http://127.0.0.1:8000 \
  --token "$PIPELINE_TOKEN" \
  --participant P001 \
  --utterances /path/to/utterances.json
```

返回的 `participant_url` 发给被试即可。

### 6. 验收

1. 用手机 4G 网络（非 WiFi）打开 `participant_url`，确认可加载
2. 填写全部标注点 → 提交成功
3. 后台登录 → 查看进度 → 导出 CSV/JSON

## 目录

- `app/` — FastAPI 后端
- `static/` — 前端页面（无需构建）
- `data/` — SQLite 数据库（自动创建）
- `scripts/` — 安装/启动脚本 + 流水线 SDK

## 端口

默认 `8000`。防火墙/安全组需放行此端口。

## 备份

```bash
cp data/app.db data/app.db.$(date +%Y%m%d-%H%M%S).bak
```
