#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request


DEFAULT_ENDPOINT = "https://atharva789--gvhmr-probe-probe-api.modal.run"
DEFAULT_VIDEO_URL = "https://raw.githubusercontent.com/zju3dv/GVHMR/main/docs/example_video/tennis.mp4"


def main() -> int:
    parser = argparse.ArgumentParser(description="Call the deployed GVHMR Modal endpoint and print timing.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Base URL of the deployed GVHMR endpoint.")
    parser.add_argument("--video-url", default=DEFAULT_VIDEO_URL, help="Public clip URL to process.")
    parser.add_argument("--static-cam", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    params = urllib.parse.urlencode(
        {
            "video_url": args.video_url,
            "static_cam": str(args.static_cam).lower(),
        }
    )
    url = f"{args.endpoint}?{params}"
    start = time.time()
    with urllib.request.urlopen(url, timeout=1800) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = round(time.time() - start, 3)

    print(json.dumps({"elapsed_s": elapsed, "url": url, "payload": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
