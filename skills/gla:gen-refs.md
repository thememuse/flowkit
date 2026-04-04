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

## Step 3: Create requests in BATCHES OF 5

**CRITICAL: Google Flow handles max 5 concurrent requests.** Submit 5, poll until done, then submit next 5.

```
For each batch of 5 entities missing media_id:
  1. Submit 5 requests:
     curl -X POST http://127.0.0.1:8100/api/requests \
       -H "Content-Type: application/json" \
       -d '{"type": "GENERATE_CHARACTER_IMAGE", "character_id": "<CID>", "project_id": "<PID>"}'
  
  2. Poll every 10s until all 5 are COMPLETED or FAILED:
     curl -s http://127.0.0.1:8100/api/requests/<RID>
  
  3. When batch done → submit next 5
```

Max wait: 120s per entity. NEVER submit all at once — causes stuck PROCESSING requests.

## Step 4: Verify

```bash
curl -s http://127.0.0.1:8100/api/projects/<PID>/characters
```

Print results table:
| Entity | Type | media_id | Status |
|--------|------|----------|--------|

All entities must have `media_id` in UUID format. If any failed, report and suggest retry.

Print: "All references ready. Run /gla:gen-images <PID> <VID> to generate scene images."
