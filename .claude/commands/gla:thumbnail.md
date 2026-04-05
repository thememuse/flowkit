Generate a thumbnail image for a project video using Google Flow image generation API.

Usage: `/gla:thumbnail <project_id> <video_id>` or `/gla:thumbnail` (prompts for selection)

If not provided, ask or list projects/videos.

## Step 1: Get project and video info

```bash
curl -s http://127.0.0.1:8100/api/projects/<PID>
curl -s "http://127.0.0.1:8100/api/videos?project_id=<PID>"
curl -s "http://127.0.0.1:8100/api/projects/<PID>/characters"
```

Note: project material, video title, and available entities (for character_names).

## Step 2: Get scenes

```bash
curl -s "http://127.0.0.1:8100/api/scenes?video_id=<VID>"
```

Print a summary table so user can see what the story is about:
| # | Order | Prompt (60 chars) | Image | Video |
|---|-------|-------------------|-------|-------|

## Step 3: Craft a hook-worthy thumbnail prompt

Analyze the scenes and story to write a compelling thumbnail prompt. Guidelines:

- **Dramatic moment**: Pick the most emotionally intense or visually striking moment from the story
- **Character focus**: Include main character(s) by name (they must have `media_id` reference images)
- **Cinematic composition**: Dramatic close-up OR action shot with clear focal point
- **Bold lighting**: Golden hour, dramatic shadows, rim light, volumetric light
- **High contrast**: Vivid colors, strong foreground/background separation
- **Leave negative space at top**: For title text overlay — keep upper 20-25% relatively clear
- **Expressive faces**: Character emotions should be clearly readable
- **Scene prompt = ACTION only**: Never describe character appearance (reference images handle that)

Example prompt structure:
```
Hero charges toward the glowing portal, arms outstretched, dramatic golden backlight, 
cinematic wide-angle composition, bold high-contrast colors, upper area clear for title text
```

Ask user: "Use this prompt? Or describe a different thumbnail idea."

## Step 4: Identify character references

From the entities list (Step 1), pick which characters/locations should be included as `character_names` for visual consistency.

**Rule**: Only include entities that already have a `media_id` (UUID format). If key characters are missing media_id, warn the user and offer to proceed without them (prompt-only generation).

## Step 5: Generate thumbnail via API

```bash
curl -X POST http://127.0.0.1:8100/api/projects/<PID>/generate-thumbnail \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "<your crafted prompt>",
    "character_names": ["Hero", "Location"],
    "aspect_ratio": "LANDSCAPE",
    "output_filename": "thumbnail.png"
  }'
```

Expected response:
```json
{
  "success": true,
  "media_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "image_url": "https://storage.googleapis.com/...",
  "output_path": "/path/to/output/project_name/thumbnail.png",
  "prompt": "..."
}
```

On error 400 (missing ref images): generate ref images first with `/gla:gen-refs`.
On error 503 (extension not connected): check `curl -s http://127.0.0.1:8100/health`.

## Step 6: Resize to YouTube thumbnail (1280x720)

```bash
PROJECT_OUTPUT="<output_path_from_response_directory>"
ffmpeg -y -i "${PROJECT_OUTPUT}/thumbnail.png" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black" \
  "${PROJECT_OUTPUT}/thumbnail_yt.png"
```

## Step 7: Optional — title text overlay

Ask user: "Add title text overlay? (default: no) If yes, enter title text (default: video title)"

**If yes:**
```bash
TITLE_TEXT="<video_title_or_user_input>"
# Escape special characters for ffmpeg drawtext
ffmpeg -y -i "${PROJECT_OUTPUT}/thumbnail_yt.png" \
  -vf "drawtext=text='${TITLE_TEXT}':fontsize=72:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=80" \
  "${PROJECT_OUTPUT}/thumbnail_titled.png"
```

Note: Text is positioned at top (y=80) to use the negative space left in the composition. If `drawtext` fails (font not found), skip silently and warn user.

## Step 8: Output

Print results:
```
Thumbnail generated for: <project_name> — <video_title>
Prompt: <prompt used>
Character refs: <list or "none">

Files saved:
  <output_path>                      — full resolution (from API)
  <output_dir>/thumbnail_yt.png      — 1280x720 YouTube size
  <output_dir>/thumbnail_titled.png  — with title overlay (if requested)
```

Suggest: "To regenerate with a different prompt, run `/gla:thumbnail <PID> <VID>` and describe a new thumbnail idea."
