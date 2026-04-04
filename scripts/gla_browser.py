#!/usr/bin/env python3
"""
GLA Browser — Launch Chrome with your DEFAULT profile (all extensions + login intact).

No Selenium, no undetected-chromedriver. Just opens your real Chrome via
remote debugging port, so the GLA extension and Google login are already there.

Usage:
    python scripts/gla_browser.py [--refresh-interval 120]

How it works:
    1. Launches YOUR Chrome (with your profile, extensions, login)
    2. Connects via Chrome DevTools Protocol (CDP) on port 9515
    3. Opens Google Flow page
    4. Periodically refreshes to keep token + reCAPTCHA alive
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

FLOW_URL = "https://labs.google/fx/tools/flow"
HEALTH_URL = "http://127.0.0.1:8100/health"
FLOW_STATUS_URL = "http://127.0.0.1:8100/api/flow/status"
DEBUG_PORT = 9515


def get_chrome_path():
    if sys.platform == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif sys.platform == "linux":
        for p in ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"]:
            if os.path.exists(p):
                return p
    return None


def get_chrome_profile():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    elif sys.platform == "linux":
        return os.path.expanduser("~/.config/google-chrome")
    return None


def check_status():
    try:
        h = json.loads(urllib.request.urlopen(HEALTH_URL, timeout=2).read())
        f = json.loads(urllib.request.urlopen(FLOW_STATUS_URL, timeout=2).read())
        return {"server": True, "ext": h.get("extension_connected", False), "auth": f.get("flow_key_present", False)}
    except Exception:
        return {"server": False, "ext": False, "auth": False}


def cdp_request(method, params=None):
    """Send a CDP command via HTTP."""
    try:
        # Get first available tab
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).read())
        ws_url = None
        for tab in tabs:
            if tab.get("type") == "page":
                ws_url = tab.get("webSocketDebuggerUrl")
                break
        return tabs
    except Exception as e:
        return None


def launch_chrome():
    """Launch Chrome with remote debugging using the user's default profile."""
    chrome = get_chrome_path()
    if not chrome:
        print("  [ERR] Chrome not found!")
        sys.exit(1)

    profile = get_chrome_profile()
    if not profile:
        print("  [ERR] Chrome profile not found!")
        sys.exit(1)

    print(f"  Chrome: {chrome}")
    print(f"  Profile: {profile}")
    print(f"  Debug port: {DEBUG_PORT}")

    # Launch Chrome with remote debugging
    cmd = [
        chrome,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        FLOW_URL,
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def refresh_via_cdp():
    """Refresh the Flow tab via CDP HTTP API."""
    try:
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).read())
        for tab in tabs:
            if "labs.google" in tab.get("url", ""):
                # Activate and reload
                urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/activate/{tab['id']}", timeout=5)
                # Use CDP Page.reload
                import http.client
                conn = http.client.HTTPConnection("127.0.0.1", DEBUG_PORT, timeout=5)
                conn.request("POST", f"/json/protocol", "")
                # Simple: just navigate to the same URL to reload
                body = json.dumps({"url": tab["url"]}).encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{DEBUG_PORT}/json/navigate/{tab['id']}?url={FLOW_URL}",
                    method="GET"
                )
                urllib.request.urlopen(req, timeout=5)
                return True
        return False
    except Exception:
        return False


def refresh_via_applescript():
    """Fallback: refresh via AppleScript on macOS."""
    if sys.platform != "darwin":
        return False
    script = '''
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "labs.google" then
                    tell t to reload
                    return
                end if
            end repeat
        end repeat
    end tell
    '''
    r = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=10)
    return r.returncode == 0


def run(refresh_interval=120):
    print("=" * 50)
    print("  GLA Browser — Your Chrome + Your Extensions")
    print("=" * 50)
    print()

    s = check_status()
    print(f"  Server: {'OK' if s['server'] else 'DOWN'}")
    print()

    # Launch Chrome
    print("  [..] Launching Chrome with your profile...")
    proc = launch_chrome()
    time.sleep(5)

    # Check if Chrome started
    if proc.poll() is not None:
        print("  [WARN] Chrome exited — it may already be running.")
        print("         If Chrome is already open, the Flow tab was added to it.")
    else:
        print("  [OK] Chrome launched")

    # Check extension status
    time.sleep(3)
    s = check_status()
    ext = "OK" if s["ext"] else "waiting..."
    auth = "OK" if s["auth"] else "waiting..."
    print(f"  ext:{ext} auth:{auth}")

    # Graceful shutdown
    def stop(sig, frame):
        print("\n  Stopped. (Chrome stays open)")
        sys.exit(0)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"\n  [LIVE] Refreshing every {refresh_interval}s. Ctrl+C to stop.\n")

    cycle = 0
    while True:
        try:
            time.sleep(refresh_interval)
            cycle += 1

            # Try AppleScript refresh (most reliable on macOS)
            ok = refresh_via_applescript()

            s = check_status()
            ext = "OK" if s["ext"] else "✗"
            auth = "OK" if s["auth"] else "✗"
            ts = time.strftime("%H:%M:%S")
            print(f"  [{ts}] #{cycle} {'refreshed' if ok else 'checked'} | ext:{ext} auth:{auth}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [ERR] {e}")
            time.sleep(10)

    print("\n  Stopped. (Chrome stays open.)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="GLA Browser — Your Chrome keep-alive")
    p.add_argument("--refresh-interval", type=int, default=120)
    run(refresh_interval=p.parse_args().refresh_interval)
