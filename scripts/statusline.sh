#!/usr/bin/env bash
# Google Flow Agent statusline for Claude Code
# Claude Code pipes session JSON to stdin — read it for real-time stats
# ANSI colors: green=32, violet/magenta=35

G="\033[32m"  # green
V="\033[35m"  # violet
R="\033[0m"   # reset

# ── Claude session info (from stdin JSON) ──
CLAUDE=""
STDIN_JSON=""

# Read stdin if available (Claude Code pipes session state)
if [ ! -t 0 ]; then
  STDIN_JSON=$(cat)
fi

if [ -n "$STDIN_JSON" ]; then
  model=$(echo "$STDIN_JSON" | jq -r '.model.display_name // empty' 2>/dev/null)
  ctx_pct=$(echo "$STDIN_JSON" | jq -r '.context_window.used_percentage // 0' 2>/dev/null | awk '{printf "%d", $1}')
  rl5h=$(echo "$STDIN_JSON" | jq -r '.rate_limits.five_hour.used_percentage // 0' 2>/dev/null | awk '{printf "%d", $1}')
  rl7d=$(echo "$STDIN_JSON" | jq -r '.rate_limits.seven_day.used_percentage // 0' 2>/dev/null | awk '{printf "%d", $1}')
  if [ -n "$model" ]; then
    CLAUDE="${model} ctx:${G}${ctx_pct}%${R} rl:${G}${rl5h}%${R}/5h ${G}${rl7d}%${R}/7d"
  fi
fi

# ── GLA info ──
BASE="http://127.0.0.1:8100"
health=$(curl -s --max-time 1 "$BASE/health" 2>/dev/null)

if [ -z "$health" ]; then
  echo -e "${CLAUDE:+$CLAUDE | }GLA: ⚠ DOWN"
  exit 0
fi

ext=$(echo "$health" | jq -r '.extension_connected // false' 2>/dev/null)
if [ "$ext" = "true" ]; then ext_icon="Ext:Ok"; else ext_icon="Ext:✗"; fi

# Flow status (credits + token freshness)
flow_info=""
flow=$(curl -s --max-time 1 "$BASE/api/flow/status" 2>/dev/null)
if [ -n "$flow" ]; then
  flow_key=$(echo "$flow" | jq -r '.flow_key_present // false' 2>/dev/null)
  if [ "$flow_key" = "true" ]; then flow_info="Auth:Ok"; else flow_info="Auth:✗"; fi
fi
credits_info=""
credits=$(curl -s --max-time 1 "$BASE/api/flow/credits" 2>/dev/null)
if [ -n "$credits" ] && [ "$credits" != "null" ]; then
  tier=$(echo "$credits" | jq -r '.data.userPaygateTier // .userPaygateTier // empty' 2>/dev/null)
  if [ -n "$tier" ]; then
    case "$tier" in
      PAYGATE_TIER_ONE) credits_info="T1" ;;
      PAYGATE_TIER_TWO) credits_info="T2" ;;
      *) credits_info="$tier" ;;
    esac
  fi
fi

# Most recent project
project=$(curl -s --max-time 1 "$BASE/api/projects" 2>/dev/null)
if [ -z "$project" ] || [ "$project" = "[]" ]; then
  echo -e "${CLAUDE:+$CLAUDE | }GLA: ${ext_icon}"
  exit 0
fi

proj_name=$(echo "$project" | jq -r '.[-1].name // "?"' 2>/dev/null)
proj_id=$(echo "$project" | jq -r '.[-1].id // ""' 2>/dev/null)

# Latest video
video=$(curl -s --max-time 1 "$BASE/api/videos?project_id=$proj_id" 2>/dev/null)
vid_id=$(echo "$video" | jq -r '.[-1].id // ""' 2>/dev/null)

if [ -z "$vid_id" ] || [ "$vid_id" = "" ]; then
  echo -e "${CLAUDE:+$CLAUDE | }GLA: ${ext_icon} $(echo "$proj_name" | cut -c1-15)"
  exit 0
fi

# Scenes
scenes=$(curl -s --max-time 1 "$BASE/api/scenes?video_id=$vid_id" 2>/dev/null)
total=$(echo "$scenes" | jq 'length' 2>/dev/null || echo 0)

# Horizontal first, fallback vertical
img_done=$(echo "$scenes" | jq '[.[] | select(.horizontal_image_status == "COMPLETED")] | length' 2>/dev/null || echo 0)
vid_done=$(echo "$scenes" | jq '[.[] | select(.horizontal_video_status == "COMPLETED")] | length' 2>/dev/null || echo 0)
up_done=$(echo "$scenes" | jq '[.[] | select(.horizontal_upscale_status == "COMPLETED")] | length' 2>/dev/null || echo 0)

if [ "$img_done" = "0" ] && [ "$vid_done" = "0" ]; then
  img_done=$(echo "$scenes" | jq '[.[] | select(.vertical_image_status == "COMPLETED")] | length' 2>/dev/null || echo 0)
  vid_done=$(echo "$scenes" | jq '[.[] | select(.vertical_video_status == "COMPLETED")] | length' 2>/dev/null || echo 0)
  up_done=$(echo "$scenes" | jq '[.[] | select(.vertical_upscale_status == "COMPLETED")] | length' 2>/dev/null || echo 0)
fi

pending=$(curl -s --max-time 1 "$BASE/api/requests/pending" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)
processing=$(curl -s --max-time 1 "$BASE/api/requests?status=PROCESSING" 2>/dev/null | jq 'length' 2>/dev/null || echo 0)

short_name=$(echo "$proj_name" | cut -c1-15)

flow_str=""
[ -n "$credits_info" ] && flow_str=" ${V}${credits_info}${R}"
[ -n "$flow_info" ] && flow_str="${flow_str} ${V}${flow_info}${R}"

# Queue: pending→processing/max
queue="${V}${pending}${R}→${V}${processing}${R}/5"

echo -e "${CLAUDE:+$CLAUDE | }GLA: ${ext_icon}${flow_str} ${short_name} ${total}sc img:${V}${img_done}${R} vid:${V}${vid_done}${R} 4K:${V}${up_done}${R} Q:${queue}"
