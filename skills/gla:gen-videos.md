Generate videos for all scenes in a video.

Usage: `/gla:gen-videos <project_id> <video_id>`

## Step 1: Pre-check — all scene images must be ready

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

**ABORT** if any scene is missing `vertical_image_media_id` (UUID) or `vertical_image_status` != `"COMPLETED"`. Tell user to run `/gla:gen-images` first.

## Step 2: Filter scenes needing video

Only scenes where `vertical_video_status` != `"COMPLETED"` or `vertical_video_media_id` is missing.

## Step 3: Create requests in BATCHES OF 5

**CRITICAL: Google Flow handles max 5 concurrent requests.** Submit 5, poll until done, then submit next 5. Video generation takes 2-5 minutes per scene.

```
For each batch of 5 scenes needing video:
  1. Submit 5 requests:
     curl -X POST http://127.0.0.1:8100/api/requests \
       -H "Content-Type: application/json" \
       -d '{"type": "GENERATE_VIDEO", "scene_id": "<SID>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "VERTICAL"}'
  
  2. Poll every 15s until all 5 are COMPLETED or FAILED
  
  3. When batch done → submit next 5
```

Max wait: 600s (10 min) per scene. NEVER submit all at once — causes stuck PROCESSING requests.

## Step 4: Verify

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

## Step 5: Output

Print results table:
| Scene | Order | video_status | video_media_id | video_url |
|-------|-------|-------------|---------------|-----------|

Print: "All videos ready. Run /gla:concat <VID> to download and merge."
