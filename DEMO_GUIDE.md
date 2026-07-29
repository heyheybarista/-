# 创建演示会话指南

## 🎯 快速创建演示会话

### 方法 1：使用专用脚本（推荐）

```bash
python scripts/create_demo_session.py \
  --base-url https://ting-dun-biao-zhu-gong-ju.onrender.com \
  --token "你的PIPELINE_TOKEN"
```

**优点：**
- ✅ 固定的演示对话内容
- ✅ 清晰的输出信息
- ✅ 默认标题带「演示会话」标识

### 方法 2：使用通用脚本

```bash
python scripts/pipeline_client.py \
  --base-url https://ting-dun-biao-zhu-gong-ju.onrender.com \
  --token "你的PIPELINE_TOKEN" \
  --participant DEMO001 \
  --title "【演示】口语任务" \
  --utterances demo_utterances.json
```

---

## 📝 演示对话内容

固定的演示对话包含：
- **10 条对话**（主试 3 条，被试 7 条）
- **4 个标注点**（2 个 incomplete，2 个 wait）
- **话题**：讲述最近遇到的有趣事情（遇到小狗的故事）

适合演示：
- 被试填写流程
- 数据导出功能
- 进度跟踪
- 主试端操作

---

## 🔑 获取 PIPELINE_TOKEN

1. 登录 Render Dashboard：https://dashboard.render.com
2. 点击你的服务
3. 左侧菜单选择 **「Environment」**
4. 找到 `PIPELINE_TOKEN`，点击 👁️ 图标查看
5. 复制该值

---

## 💡 使用场景

### 演示前准备
```bash
# 1. 清理旧的测试会话（可选）
# 在主试端点击「清理未提交测试会话」

# 2. 创建演示会话
python scripts/create_demo_session.py \
  --base-url https://ting-dun-biao-zhu-gong-ju.onrender.com \
  --token "你的PIPELINE_TOKEN"

# 3. 在主试端复制被试链接
```

### 每次演示时
1. 打开主试端：https://ting-dun-biao-zhu-gong-ju.onrender.com
2. 登录（admin / admin）
3. 找到「【演示会话】口语任务」
4. 点击「详情」→「复制链接」
5. 在另一个浏览器/手机打开被试端演示

### 演示后清理
- 如果需要重新演示，可以在主试端点击「重置提交」
- 或者删除旧会话，重新运行脚本创建新的

---

## 🎭 演示要点

### 展示被试端功能
1. 打开被试链接，展示指导语
2. 演示填写流程：
   - 选择原因类别
   - 填写心理过程描述
   - 点击置信度
3. 显示自动保存提示
4. 完成所有标注后提交

### 展示主试端功能
1. 查看会话列表和进度
2. 实时查看被试填写进度（刷新列表）
3. 导出 CSV/JSON 数据
4. 演示重置和删除功能
5. 展示设置页面（指导语、类别管理）

---

## 📌 注意事项

1. **Render 免费层限制**：
   - 15 分钟无活动会休眠
   - 首次访问需要 50 秒冷启动
   - 演示前提前打开网站预热

2. **演示会话标识**：
   - 被试编号：DEMO001
   - 标题：【演示会话】口语任务
   - 方便识别和管理

3. **快速重置**：
   - 使用「重置提交」而不是删除+重建
   - 保持被试链接不变

---

## 🆘 常见问题

### Q: 每次都要重新创建演示会话吗？
A: 不需要。创建一次后，可以用「重置提交」功能反复使用同一个会话。

### Q: 能否修改演示对话的内容？
A: 可以。编辑 `demo_utterances.json` 文件，或修改 `scripts/create_demo_session.py` 中的 `DEMO_DATA`。

### Q: 如何区分演示会话和正式数据？
A: 演示会话使用特殊前缀：
- 被试编号：DEMO001
- 标题：【演示会话】

导出数据时可以根据这些字段过滤。

---

## 🔗 相关文件

- [scripts/create_demo_session.py](scripts/create_demo_session.py) - 演示会话创建脚本
- [demo_utterances.json](demo_utterances.json) - 固定的演示对话数据
- [scripts/pipeline_client.py](scripts/pipeline_client.py) - 通用会话创建脚本
- [DEPLOY.md](DEPLOY.md) - Render 部署指南
- [README.md](README.md) - 完整项目文档
