import re
import secrets

EASYTURN_LABEL_RE = re.compile(r"<(\w+)>")


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def parse_easyturn(raw: str) -> tuple[str, str | None]:
    """
    输入："因为小时候<incomplete><|endoftext|>"
    返回：(clean_text, label)  如 ("因为小时候", "incomplete")
    """
    clean = re.sub(r"<\|endoftext\|>", "", raw, flags=re.IGNORECASE).strip()
    match = EASYTURN_LABEL_RE.findall(clean)
    label = match[-1].lower() if match else None
    if label:
        clean = re.sub(rf"\s*<{re.escape(label)}>\s*$", "", clean).strip()
    return clean, label


# 默认配置——与 models/settings 保持一致，也用于首次初始化
DEFAULT_INSTRUCTION = """**任务说明**
下面呈现的是你刚才与主试完成英语口语任务时的对话转录。系统已在你的部分发言处标出可能与「未说完 / 需要等待」相关的位置（由话轮模型自动标记）。

**请你做什么**
请依次查看每一处标记。结合前后对话，回忆当时你为什么会这样停顿、犹豫或没有继续说完，并填写：
1）最符合的原因类别；
2）当时的原因与心理过程（请写具体一些，例如你在想哪个词、哪句结构、还是在组织内容）；
3）你对上述描述的确信程度（1–7）。

**描述建议**
- 请尽量描述「当下」的想法，而不是事后合理化。
- 建议每处约 20–100 字；若确实记不清，可如实写"记不清"，并在置信度上选择较低分数。
- 主试的发言仅帮助你回忆语境，无需对主试发言作答。

**提交**
所有标记处填写完成后，点击顶部「提交」。提交后不可再修改。填写过程中会自动保存进度，可中途关闭，稍后用同一链接继续。"""

DEFAULT_ANNOTATABLE_LABELS = ["incomplete", "wait"]

DEFAULT_REASON_CATEGORIES = [
    {"value": "lexical", "label": "找词 / 词汇提取"},
    {"value": "syntax", "label": "句法 / 句子组织"},
    {"value": "thinking", "label": "内容思考"},
    {"value": "intention_shift", "label": "意图切换"},
    {"value": "interactive", "label": "互动 / 等待对方"},
    {"value": "external", "label": "外部干扰"},
    {"value": "other", "label": "其他"},
]

LABEL_HINTS = {
    "incomplete": "未说完",
    "wait": "等待",
    "complete": "完整",
    "backchannel": "附和",
}
