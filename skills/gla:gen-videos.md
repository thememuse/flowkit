Generate videos for all scenes in a video.

Usage: `/gla:gen-videos <project_id> <video_id>`

## Step 1: Pre-check — all scene images must be ready

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

**ABORT** if any scene is missing `vertical_image_media_id` (UUID) or `vertical_image_status` != `"COMPLETED"`. Tell user to run `/gla:gen-images` first.

## Step 2: Filter scenes needing video

Only scenes where `vertical_video_status` != `"COMPLETED"` or `vertical_video_media_id` is missing.

## Step 3: Submit ALL requests at once

The server handles throttling automatically (max 5 concurrent, 10s cooldown). Submit everything in one batch call. Video generation takes 2-5 minutes per scene.

```bash
curl -X POST http://127.0.0.1:8100/api/requests/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"type": "GENERATE_VIDEO", "scene_id": "<SID1>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "VERTICAL"},
      {"type": "GENERATE_VIDEO", "scene_id": "<SID2>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "VERTICAL"}
    ]
  }'
```

Build the `requests` array from ALL scenes filtered in Step 2. Do NOT manually batch or loop.

Poll aggregate status every 30s until done (videos take longer):

```bash
curl -s "http://127.0.0.1:8100/api/requests/batch-status?video_id=<VID>&type=GENERATE_VIDEO"
# Wait for: "done": true
# If "all_succeeded": false → some failed, check individual failures
```

## Step 4: Verify

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

## Step 5: Output

Print results table:
| Scene | Order | video_status | video_media_id | video_url |
|-------|-------|-------------|---------------|-----------|

Print: "All videos ready. Run /gla:concat <VID> to download and merge."
