#!/usr/bin/env python3
"""
流水线创建会话示例。
使用方式（在 VAD/ASR/EasyTurn 结束后调用）：
    python scripts/pipeline_client.py \\
        --base-url http://127.0.0.1:8000 \\
        --token "$PIPELINE_TOKEN" \\
        --participant P001 \\
        --utterances data.json
"""
import argparse, json, sys, requests


def main():
    parser = argparse.ArgumentParser(description="推送口语会话到停顿标注工具")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="PIPELINE_TOKEN")
    parser.add_argument("--participant", default="", help="被试编号")
    parser.add_argument("--title", default="口语任务")
    parser.add_argument("--utterances", required=True, help="JSON 文件路径，含 utterances 数组")
    parser.add_argument("--labels", default="incomplete,wait", help="本场可标注标签，逗号分隔")
    args = parser.parse_args()

    with open(args.utterances, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload = {
        "external_participant_id": args.participant,
        "title": args.title,
        "annotatable_labels": [x.strip() for x in args.labels.split(",") if x.strip()],
        "utterances": data.get("utterances", data),
    }

    resp = requests.post(
        f"{args.base_url.rstrip('/')}/api/pipeline/sessions",
        json=payload,
        headers={"Authorization": f"Bearer {args.token}"},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Session created: {result['session_id']}")
    print(f"Participant URL: {result['participant_url']}")
    print(f"Admin URL:      {result['admin_url']}")
    print(f"Target count:   {result['target_count']}")
    return result


if __name__ == "__main__":
    main()
