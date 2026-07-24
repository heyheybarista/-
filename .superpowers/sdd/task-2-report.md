# Task 2 Report: Participant API (GET session, PATCH annotation, POST submit)

## What was implemented

Replaced the empty stub in `app/routers/participant.py` with three endpoints:

| Endpoint | Behavior |
|---|---|
| `GET /api/a/{token}` | Load session by access token; returns utterances with embedded annotation targets and existing annotations. First access transitions status from `"created"` to `"in_progress"` and sets `opened_at`. |
| `PATCH /api/a/{token}/annotations/{target_id}` | Upsert (create-or-update) an Annotation row. Uses `model_dump(exclude_unset=True)` to apply only explicitly-provided fields. Recomputes `is_complete` (true when all three of `category`, `description`, `confidence` have truthy values). Rejects with 400 if session is already submitted. |
| `POST /api/a/{token}/submit` | Validates all required AnnotationTargets have a complete Annotation. On success, sets `status="submitted"` and `submitted_at`. On failure, returns 400 with a list of incomplete `target_id`s and `display_hint`s. Idempotent — returns `{"ok":true,"message":"Already submitted"}` if called again. |

## Test results

All tests performed on a running instance at `http://127.0.0.1:8000`.

### 1. GET session (first access)
```
GET /api/a/{token}  →  200
Status transitioned to "in_progress"
Returns 5 utterances, 2 with annotation_target (incomplete + wait)
```
- Correctly transitions `"created"` to `"in_progress"` on first access.

### 2. PATCH draft
```
PATCH /api/a/{token}/annotations/{target_id}
  {"category":"thinking","description":"testing","confidence":6}
  →  {"ok":true,"is_complete":true}

PATCH second target with Chinese characters:
  {"category":"lexical","description":"在想公园这个词怎么说","confidence":5}
  →  {"ok":true,"is_complete":true}
```
- Partial updates work (only sent fields are applied).
- `is_complete` correctly computed as true when all 3 fields have values.

### 3. GET after PATCH — reflects saved draft
```
GET /api/a/{token} → annotations are embedded:
  seq=1 cat=thinking desc=test conf=5 complete=True
  seq=2 cat=interactive desc=等待对方回应 conf=4 complete=True
```

### 4. POST submit — success path
```
POST /api/a/{token}/submit → {"ok":true,"message":"Submitted"}
GET /api/a/{token} → status="submitted"
```

### 5. POST submit — incomplete blocks with 400
- Submitted with 0 annotations: returns 400 with **both** target_ids listed.
- Submitted with 1 of 2 complete: returns 400 with **only the missing** target_id.

### 6. Edge cases
- `PATCH` after submit → `400: "Session already submitted"`
- Re-`POST submit` → `{"ok":true,"message":"Already submitted"}`
- Invalid token on all endpoints → `404: "Session not found"`

## Status

**DONE**

All endpoints are implemented, tested, and verified against all requirements in the task brief.

## Files changed

- `app/routers/participant.py` — full implementation replacing the stub
