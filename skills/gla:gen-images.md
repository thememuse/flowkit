Generate scene images for all scenes in a video.

Usage: `/gla:gen-images <project_id> <video_id>`

If not provided, ask or list projects/videos.

## Step 1: Pre-check — all references must be ready

```bash
curl -s http://127.0.0.1:8100/api/projects/<PID>/characters
```

**ABORT** if any entity is missing `media_id`. Tell user to run `/gla:gen-refs <PID>` first.

## Step 2: Get scenes

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

Filter to scenes where `vertical_image_status` != `"COMPLETED"` or `vertical_image_media_id` is missing/not UUID.

## Step 3: Submit ALL requests at once

The server handles throttling automatically (max 5 concurrent, 10s cooldown). Submit everything in one batch call:

```bash
curl -X POST http://127.0.0.1:8100/api/requests/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"type": "GENERATE_IMAGE", "scene_id": "<SID1>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "VERTICAL"},
      {"type": "GENERATE_IMAGE", "scene_id": "<SID2>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "VERTICAL"}
    ]
  }'
```

Build the `requests` array from ALL scenes filtered in Step 2. Do NOT manually batch or loop.

Poll aggregate status every 15s until done:

```bash
curl -s "http://127.0.0.1:8100/api/requests/batch-status?video_id=<VID>&type=GENERATE_IMAGE"
# Wait for: "done": true
# If "all_succeeded": false → some failed, check individual failures
```

## Step 4: Verify media_ids are UUID

After all complete, check each scene:
```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

If any `vertical_image_media_id` starts with `CAMS` or is not UUID format, fix it by extracting UUID from `vertical_image_url`:
```bash
# Extract UUID from URL path: /image/{UUID}?...
curl -X PATCH http://127.0.0.1:8100/api/scenes/<SID> \
  -H "Content-Type: application/json" \
  -d '{"vertical_image_media_id": "<extracted_uuid>"}'
```

## Step 5: Output

Print results table:
| Scene | Order | image_status | media_id (UUID) |
|-------|-------|-------------|----------------|

Print: "All scene images ready. Run /gla:gen-videos <PID> <VID> to generate videos."
