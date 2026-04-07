Generate reference images for all entities in a project.

Usage: `/gla:gen-refs <project_id>`

If no project_id provided, ask the user or list projects via `GET /api/projects`.

## Step 1: Check health

```bash
curl -s http://127.0.0.1:8100/health
```
Must have `extension_connected: true`. Abort if not.

## Step 2: Get entities

```bash
curl -s http://127.0.0.1:8100/api/projects/<PID>/characters
```

Filter to entities that do NOT yet have `media_id` (UUID format). Skip ones already done.

## Step 3: Submit ALL requests at once

The server handles throttling automatically (max 5 concurrent, 10s cooldown). Submit everything in one batch call:

```bash
curl -X POST http://127.0.0.1:8100/api/requests/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"type": "GENERATE_CHARACTER_IMAGE", "character_id": "<CID1>", "project_id": "<PID>"},
      {"type": "GENERATE_CHARACTER_IMAGE", "character_id": "<CID2>", "project_id": "<PID>"}
    ]
  }'
```

Build the `requests` array from ALL entities missing `media_id` in Step 2. Do NOT manually batch or loop.

Poll aggregate status every 15s until done:

```bash
curl -s "http://127.0.0.1:8100/api/requests/batch-status?project_id=<PID>&type=GENERATE_CHARACTER_IMAGE"
# Wait for: "done": true
# If "all_succeeded": false → some failed, check individual failures
```

## Step 4: Verify

```bash
curl -s http://127.0.0.1:8100/api/projects/<PID>/characters
```

Print results table:
| Entity | Type | media_id | Status |
|--------|------|----------|--------|

All entities must have `media_id` in UUID format. If any failed, report and suggest retry.

Print: "All references ready. Run /gla:gen-images <PID> <VID> to generate scene images."
