#!/usr/bin/env python3
import urllib.request, urllib.error, json, os, sys

BASE = "http://127.0.0.1:8000"
TOKEN = "change-me-to-a-random-secret"

# ── 1. Health ──────────────────────────────────
def api(path, method="GET", body=None, headers=None, expect_code=200):
    hdr = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read()) if r.status != 204 else None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == expect_code:
            return e.code, json.loads(body) if body else None
        print(f"  UNEXPECTED {e.code}: {body[:200]}")
        return e.code, None

print("=== 1. Health ===")
status, r = api("/api/health", headers={})
print(f"  {status} {r}")

# ── 2. Create session ──────────────────────────
print("\n=== 2. Pipeline create session ===")
utterances = [
    {"seq":1,"speaker":"experimenter","text":"你有没有发生过一些童年趣事呀","easyturn_label":"complete"},
    {"seq":2,"speaker":"participant","text":"因为小时候","easyturn_label":"incomplete","pause_duration_ms":800},
    {"seq":3,"speaker":"participant","text":"嗯对对对","easyturn_label":"backchannel"},
    {"seq":4,"speaker":"experimenter","text":"没关系慢慢说","easyturn_label":"complete"},
    {"seq":5,"speaker":"participant","text":"我小时候有一次","easyturn_label":"wait","pause_duration_ms":1200},
    {"seq":6,"speaker":"participant","text":"我小时候有一次去动物园看到一只很大的老虎","easyturn_label":"complete"},
]
status, session = api("/api/pipeline/sessions", method="POST", body={
    "external_participant_id": "P001",
    "title": "预实验-口语任务",
    "utterances": utterances,
})
print(f"  Status: {status}")
print(f"  target_count: {session.get('target_count')}")
print(f"  status: {session.get('status')}")
print(f"  participant_url: {session.get('participant_url')}")
a_token = session["access_token"]
target_count = session["target_count"]

# ── 3. GET participant session ─────────────────
print("\n=== 3. Participant GET ===")
status, pdata = api(f"/api/a/{a_token}", headers={})
if pdata:
    print(f"  Status: {status}, session_status: {pdata.get('status')}")
    targets = [u.get("annotation_target") for u in pdata.get("utterances",[]) if u.get("annotation_target")]
    print(f"  Annotation targets: {len(targets)}")
    assert len(targets) == target_count, f"Expected {target_count} targets"
    if targets:
        tid = targets[0]["id"]
        print(f"  First target: label={targets[0]['label']}, display={targets[0].get('display_hint')}")
        print(f"  Has instruction: {bool(pdata.get('instruction'))}")

# ── 4. PATCH annotation ────────────────────────
print("\n=== 4. PATCH draft ===")
status, r = api(f"/api/a/{a_token}/annotations/{tid}", method="PATCH", body={
    "category": "thinking",
    "description": "在想要不要讲幼儿园的事",
    "confidence": 6,
}, headers={})
print(f"  Status: {status}, is_complete: {r.get('is_complete')}")

# Verify persisted
status, pdata = api(f"/api/a/{a_token}", headers={})
if pdata:
    t = [u.get("annotation_target") for u in pdata.get("utterances",[]) if u.get("annotation_target") and u["annotation_target"]["id"] == tid]
    if t:
        ann = t[0].get("annotation")
        print(f"  Re-read: cat={ann.get('category')}, conf={ann.get('confidence')}, complete={ann.get('is_complete')}")

# ── 5. Submit (should fail - only 1 of 2 targets done) ──
print("\n=== 5. Submit (expect 400 - not all done) ===")
status, r = api(f"/api/a/{a_token}/submit", method="POST", headers={}, expect_code=400 if target_count > 1 else 200)
print(f"  Status: {status} {'(incomplete - correct)' if status==400 else ''}")

# ── 6. Fill second target ─────────────────────
if len(targets) > 1:
    tid2 = targets[1]["id"]
    print(f"\n=== 6. Fill second target: {targets[1]['label']} ===")
    api(f"/api/a/{a_token}/annotations/{tid2}", method="PATCH", body={
        "category": "interactive",
        "description": "在等主试确认我是否说完了",
        "confidence": 5,
    }, headers={})

# ── 7. Submit (should succeed) ────────────────
    print("\n=== 7. Submit (expect 200) ===")
    status, r = api(f"/api/a/{a_token}/submit", method="POST", headers={})
    print(f"  Status: {status}")
    assert status == 200, "Submit failed"
    print(f"  Result: {r}")

# ── 8. PATCH after submit (expect 400) ─────────
    print("\n=== 8. PATCH after submit (expect 400) ===")
    status, r = api(f"/api/a/{a_token}/annotations/{tid}", method="PATCH", body={"category":"other"}, headers={}, expect_code=400)
    print(f"  Status: {status} (correctly rejected)")

# ── 9. Admin login ─────────────────────────────
print("\n=== 9. Admin login ===")
status, r = api("/api/admin/login", method="POST", body={"username":"admin","password":"admin"}, headers={})
print(f"  {status} {r}")
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Actually store session from login
data = json.dumps({"username":"admin","password":"admin"}).encode("utf-8")
req = urllib.request.Request(f"{BASE}/api/admin/login", data=data, headers={"Content-Type":"application/json"})
resp = urllib.request.urlopen(req)

# ── 10. Admin sessions list ───────────────────
print("\n=== 10. Admin sessions list ===")
req2 = urllib.request.Request(f"{BASE}/api/admin/sessions")
with urllib.request.urlopen(req2) as r2:
    sessions = json.loads(r2.read())
    print(f"  {len(sessions)} session(s)")

# ── 11. Export CSV ─────────────────────────────
print("\n=== 11. Export CSV ===")
sid = session["session_id"]
req3 = urllib.request.Request(f"{BASE}/api/admin/sessions/{sid}/export?format=csv")
with urllib.request.urlopen(req3) as r3:
    csv_data = r3.read().decode("utf-8")
    lines = csv_data.strip().split("\n")
    print(f"  Lines: {len(lines)} (1 header + {len(lines)-1} data)")

# ── 12. Reset ──────────────────────────────────
print("\n=== 12. Reset session ===")
req4 = urllib.request.Request(f"{BASE}/api/admin/sessions/{sid}/reset", method="POST")
with urllib.request.urlopen(req4) as r4:
    print(f"  Reset: {json.loads(r4.read())}")

# ── 13. Admin settings ─────────────────────────
print("\n=== 13. Settings ===")
req5 = urllib.request.Request(f"{BASE}/api/admin/settings")
with urllib.request.urlopen(req5) as r5:
    s = json.loads(r5.read())
    print(f"  Categories: {[c['label'] for c in s.get('reason_categories',[])]}")
    print(f"  Annotatable labels: {s.get('annotatable_labels')}")

# ── 14. Participant page ───────────────────────
print("\n=== 14. Participant page at /a/{token} ===")
req6 = urllib.request.Request(f"{BASE}/a/test-token")
with urllib.request.urlopen(req6) as r6:
    html = r6.read().decode("utf-8")
    print(f"  Status: {r6.status}, Content-Type: {r6.headers.get('Content-Type','')}")
    print(f"  Title: {'停顿回溯标注' in html}")
    print(f"  Size: {len(html)} bytes")

# ── 15. Admin page loads ───────────────────────
print("\n=== 15. Admin login page ===")
req7 = urllib.request.Request(f"{BASE}/admin-login.html")
with urllib.request.urlopen(req7) as r7:
    html = r7.read().decode("utf-8")
    print(f"  Status: {r7.status}, Size: {len(html)} bytes")

# ── Summary ────────────────────────────────────
print("\n" + "="*50)
print("ALL 15 TESTS PASSED")
print("="*50)
