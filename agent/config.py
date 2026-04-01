"""Configuration constants."""
import os
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────
BASE_DIR = Path(os.environ.get("FLOW_AGENT_DIR", Path(__file__).parent.parent))
DB_PATH = BASE_DIR / "flow_agent.db"

# ─── API Server ──────────────────────────────────────────────
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8100"))

# ─── WebSocket Server (extension connects here) ─────────────
WS_HOST = os.environ.get("WS_HOST", "127.0.0.1")
WS_PORT = int(os.environ.get("WS_PORT", "9222"))

# ─── Google Flow API ────────────────────────────────────────
GOOGLE_FLOW_API = "https://aisandbox-pa.googleapis.com"
GOOGLE_API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"
RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

# ─── Worker ──────────────────────────────────────────────────
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
VIDEO_POLL_TIMEOUT = int(os.environ.get("VIDEO_POLL_TIMEOUT", "420"))

# ─── Video Model Keys ───────────────────────────────────────
VIDEO_MODELS = {
    "PAYGATE_TIER_TWO": {
        "frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_1_i2v_s_fast_ultra",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_i2v_s_fast_portrait_ultra",
        },
        "start_end_frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_1_i2v_s_fast_ultra_fl",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_i2v_s_fast_portrait_ultra_fl",
        },
        "reference_frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_0_r2v_fast_ultra",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_0_r2v_fast_portrait_ultra",
        },
    },
    "PAYGATE_TIER_ONE": {
        "frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_1_i2v_s_fast",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_i2v_s_fast_portrait",
        },
        "start_end_frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_1_i2v_s_fast_fl",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_i2v_s_fast_portrait_fl",
        },
        "reference_frame_2_video": {
            "VIDEO_ASPECT_RATIO_LANDSCAPE": "veo_3_1_r2v_fast",
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_r2v_fast_portrait",
        },
    },
}

UPSCALE_MODELS = {
    "VIDEO_RESOLUTION_4K": "veo_3_1_upsampler_4k",
    "VIDEO_RESOLUTION_1080P": "veo_3_1_upsampler_1080p",
}

# ─── API Endpoints ───────────────────────────────────────────
ENDPOINTS = {
    "generate_images": "/v1/projects/{project_id}/flowMedia:batchGenerateImages",
    "generate_video": "/v1/video:batchAsyncGenerateVideoStartImage",
    "generate_video_start_end": "/v1/video:batchAsyncGenerateVideoStartAndEndImage",
    "generate_video_references": "/v1/video:batchAsyncGenerateVideoReferenceImages",
    "upscale_video": "/v1/video:batchAsyncGenerateVideoUpsampleVideo",
    "upscale_image": "/v1/flow/upsampleImage",
    "upload_image": "/v1:uploadUserImage",
    "check_video_status": "/v1/video:batchCheckAsyncVideoGenerationStatus",
    "get_credits": "/v1/credits",
    "get_media": "/v1/media/{media_id}",
}

# ─── Header Randomization Pools ─────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
]

CHROME_VERSIONS = [
    '"Google Chrome";v="109", "Chromium";v="109"',
    '"Google Chrome";v="110", "Chromium";v="110"',
    '"Google Chrome";v="111", "Chromium";v="111"',
    '"Google Chrome";v="113", "Not-A.Brand";v="24"',
    '"Google Chrome";v="120", "Not-A.Brand";v="24"',
    '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
]

BROWSER_VALIDATIONS = [
    "qSH0RgPhYS+tEktJTy2ahvLDO9s=",
    "rTK1ShQiZT+uFlkKUz3bivMEP0t=",
    "sUL2TiRjAU+vGmlLV04cjwNFQ1u=",
    "tVM3UjSkBV+wHnmMW15dkxOGR2v=",
    "uWN4VkTlCW+xIonNX26elySHS3w=",
    "vXO5WlUmDX+yJpoOY37fmzPIT4x=",
]

CLIENT_DATA = [
    "CMXbygE=",
    "CNYcywE=",
    "CObdzAE=",
    "CPheywE=",
    "CQjfzQE=",
    "CRkgzRE=",
]
