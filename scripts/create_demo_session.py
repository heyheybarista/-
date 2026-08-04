#!/usr/bin/env python3
"""
创建固定的演示会话
使用方式：
    python scripts/create_demo_session.py --base-url https://ting-dun-biao-zhu-gong-ju.onrender.com --token "你的PIPELINE_TOKEN"
"""
import argparse
import json
import sys
import requests
import os

# 固定的演示对话数据
DEMO_DATA = {
    "utterances": [
        {
            "seq": 1,
            "speaker": "experimenter",
            "text": "请你讲述一件你最近遇到的有趣的事情",
            "easyturn_label": "complete"
        },
        {
            "seq": 2,
            "speaker": "participant",
            "text": "嗯",
            "easyturn_label": "incomplete",
            "pause_duration_ms": 650
        },
        {
            "seq": 3,
            "speaker": "participant",
            "text": "最近我",
            "easyturn_label": "incomplete",
            "pause_duration_ms": 800
        },
        {
            "seq": 4,
            "speaker": "participant",
            "text": "去超市买东西的时候",
            "easyturn_label": "wait",
            "pause_duration_ms": 1200
        },
        {
            "seq": 5,
            "speaker": "participant",
            "text": "遇到了一只特别可爱的小狗",
            "easyturn_label": "complete"
        },
        {
            "seq": 6,
            "speaker": "experimenter",
            "text": "哦是吗，然后呢",
            "easyturn_label": "complete"
        },
        {
            "seq": 7,
            "speaker": "participant",
            "text": "那只狗",
            "easyturn_label": "incomplete",
            "pause_duration_ms": 700
        },
        {
            "seq": 8,
            "speaker": "participant",
            "text": "它一直跟着我",
            "easyturn_label": "wait",
            "pause_duration_ms": 900
        },
        {
            "seq": 9,
            "speaker": "participant",
            "text": "我就给它买了一些零食",
            "easyturn_label": "complete"
        },
        {
            "seq": 10,
            "speaker": "experimenter",
            "text": "听起来很有趣",
            "easyturn_label": "complete"
        }
    ]
}


def main():
    parser = argparse.ArgumentParser(description="创建固定的演示会话")
    parser.add_argument("--base-url", required=True, help="服务地址，如 https://xxx.onrender.com")
    parser.add_argument("--token", required=True, help="PIPELINE_TOKEN")
    parser.add_argument("--participant", default="DEMO001", help="被试编号（默认：DEMO001）")
    parser.add_argument("--title", default="【演示会话】口语任务", help="会话标题")
    args = parser.parse_args()

    payload = {
        "external_participant_id": args.participant,
        "title": args.title,
        "annotatable_labels": ["incomplete", "wait"],
        "utterances": DEMO_DATA["utterances"]
    }

    url = f"{args.base_url.rstrip('/')}/api/pipeline/sessions"
    headers = {
        "Authorization": f"Bearer {args.token}",
        "Content-Type": "application/json"
    }

    print(f"📤 正在创建演示会话...")
    print(f"   服务地址: {args.base_url}")
    print(f"   被试编号: {args.participant}")
    print(f"   会话标题: {args.title}")
    print()

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        print("✅ 演示会话创建成功！")
        print(f"\n📋 会话信息:")
        print(f"   Session ID: {result.get('session_id', 'N/A')}")
        print(f"   被试编号: {result.get('external_participant_id', 'N/A')}")
        print(f"   标题: {result.get('title', 'N/A')}")
        print(f"\n🔗 主试说话人审核:")
        print(f"   {result.get('admin_url', 'N/A')}")
        print()
        print("💡 提示：确认主试话语后，页面才会生成被试链接")

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 错误: {e}")
        if e.response is not None:
            print(f"   状态码: {e.response.status_code}")
            print(f"   响应: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
