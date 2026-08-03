#!/usr/bin/env python3
"""End-to-end smoke test for the multi-pause annotation workflow."""

import csv
import http.cookiejar
import io
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USERNAME = os.environ.get("SMOKE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "admin")


def load_env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return None


PIPELINE_TOKEN = load_env_value("PIPELINE_TOKEN") or "change-me"
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cookie_jar)
)


def request(path, method="GET", body=None, pipeline_auth=False):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if pipeline_auth:
        headers["Authorization"] = f"Bearer {PIPELINE_TOKEN}"
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    try:
        with opener.open(req, timeout=120) as response:
            raw = response.read()
            return response.status, response.headers, parse_body(raw, response.headers)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, error.headers, parse_body(raw, error.headers)


def parse_body(raw, headers):
    if not raw:
        return None
    text = raw.decode("utf-8-sig")
    if "json" in headers.get("Content-Type", ""):
        return json.loads(text)
    return text


def expect(status, expected, context, body=None):
    if status != expected:
        raise AssertionError(
            f"{context}: expected HTTP {expected}, got {status}: {body}"
        )


def main():
    session_id = None
    admin_logged_in = False
    try:
        status, _, health = request("/api/health")
        expect(status, 200, "health", health)
        assert health == {"status": "ok"}
        print("[1/9] Health check passed")

        payload = {
            "external_participant_id": "SMOKE-MULTI-PAUSE",
            "title": "Multi-pause smoke test",
            "utterances": [
                {
                    "seq": 1,
                    "speaker": "experimenter",
                    "text": "请描述这张图片。",
                    "easyturn_label": "complete",
                },
                {
                    "seq": 2,
                    "speaker": "participant",
                    "text": "我看到一个人在窗边思考。",
                    "raw_text": "我看到一个人<PAUSE:0.42s>在窗边<PAUSE:1.15s>思考。",
                    "easyturn_label": "complete",
                    "pauses": [
                        {"duration": 0.42, "level": "medium", "position": 6},
                        {"duration": 1.15, "level": "long", "position": 22},
                    ],
                },
                {
                    "seq": 3,
                    "speaker": "participant",
                    "text": "然后他转过身。",
                    "easyturn_label": "complete",
                    "extra": {
                        "pauses": [
                            {"duration": 0.63, "level": "medium"}
                        ]
                    },
                },
            ],
        }
        status, _, created = request(
            "/api/pipeline/sessions",
            method="POST",
            body=payload,
            pipeline_auth=True,
        )
        expect(status, 200, "create session", created)
        assert created["target_count"] == 3, created
        session_id = created["session_id"]
        access_token = created["access_token"]
        print("[2/9] Session with three pause targets created")

        status, _, participant = request(f"/api/a/{access_token}")
        expect(status, 200, "participant session", participant)
        targets = [
            target
            for utterance in participant["utterances"]
            for target in utterance.get("annotation_targets", [])
        ]
        assert len(targets) == 3, participant
        multi_utterance = participant["utterances"][1]
        assert [
            target["target_index"]
            for target in multi_utterance["annotation_targets"]
        ] == [0, 1]
        print("[3/9] Participant API returned all targets in order")

        first_target = targets[0]
        status, _, patched = request(
            f"/api/a/{access_token}/annotations/{first_target['id']}",
            method="PATCH",
            body={
                "category": "thinking",
                "description": "正在组织图片描述。",
                "confidence": 6,
            },
        )
        expect(status, 200, "patch first annotation", patched)
        assert patched["is_complete"] is True

        status, _, incomplete = request(
            f"/api/a/{access_token}/submit", method="POST"
        )
        expect(status, 400, "incomplete submission", incomplete)
        assert len(incomplete["detail"]["incomplete"]) == 2
        print("[4/9] Incomplete submission was rejected")

        for index, target in enumerate(targets[1:], start=2):
            status, _, patched = request(
                f"/api/a/{access_token}/annotations/{target['id']}",
                method="PATCH",
                body={
                    "category": "thinking",
                    "description": f"第 {index} 个停顿的回溯说明。",
                    "confidence": 5,
                },
            )
            expect(status, 200, f"patch target {index}", patched)
            assert patched["is_complete"] is True

        status, _, submitted = request(
            f"/api/a/{access_token}/submit", method="POST"
        )
        expect(status, 200, "complete submission", submitted)
        print("[5/9] Complete session submitted")

        status, _, rejected = request(
            f"/api/a/{access_token}/annotations/{first_target['id']}",
            method="PATCH",
            body={"confidence": 4},
        )
        expect(status, 400, "patch after submit", rejected)
        print("[6/9] Post-submission edits were rejected")

        status, _, login = request(
            "/api/admin/login",
            method="POST",
            body={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        expect(status, 200, "admin login", login)
        admin_logged_in = True

        status, _, detail = request(f"/api/admin/sessions/{session_id}")
        expect(status, 200, "admin session detail", detail)
        admin_targets = [
            target
            for utterance in detail["utterances"]
            for target in utterance.get("targets", [])
        ]
        assert len(admin_targets) == 3, detail
        assert all(target["annotation"]["is_complete"] for target in admin_targets)
        print("[7/9] Admin detail returned every completed target")

        status, _, csv_text = request(
            f"/api/admin/sessions/{session_id}/export?format=csv"
        )
        expect(status, 200, "CSV export", csv_text)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        target_rows = [row for row in rows if row["target_label"]]
        assert len(rows) == 4, rows
        assert len(target_rows) == 3, target_rows
        assert {row["target_index"] for row in target_rows} == {"0", "1"}
        print("[8/9] CSV export contains one row per target")

        status, _, participant_html = request(f"/a/{access_token}")
        expect(status, 200, "participant page", participant_html)
        assert "annotation_targets" in participant_html
        print("[9/9] Participant page uses the plural target contract")
    finally:
        if session_id and not admin_logged_in:
            status, _, _ = request(
                "/api/admin/login",
                method="POST",
                body={
                    "username": ADMIN_USERNAME,
                    "password": ADMIN_PASSWORD,
                },
            )
            admin_logged_in = status == 200
        if session_id and admin_logged_in:
            status, _, deleted = request(
                f"/api/admin/sessions/{session_id}", method="DELETE"
            )
            if status != 200:
                print(
                    f"WARNING: could not delete smoke session {session_id}: "
                    f"HTTP {status} {deleted}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"SMOKE TEST FAILED: {error}", file=sys.stderr)
        raise
    print("ALL SMOKE TESTS PASSED")
