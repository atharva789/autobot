from __future__ import annotations
import json
import os
import uuid
import subprocess
from pathlib import Path

_ER16_PROMPT = """You are an embodied-reasoning assistant.
Given a task description, return ONLY valid JSON with keys:
task_goal (str), affordances (list[str]), success_criteria (str),
search_queries (list[str], top 3 YouTube queries to find reference videos).
Task: {prompt}"""


class IngestService:
    def __init__(
        self,
        gemini_api_key: str,
        youtube_api_key: str,
        supabase_url: str,
        supabase_key: str,
    ) -> None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            self._gemini_model = genai.GenerativeModel("gemini-robotics-er-1.6")
        except ImportError:
            from unittest.mock import MagicMock
            self._gemini_model = MagicMock()
        self._youtube_api_key = youtube_api_key

    def analyze_prompt(self, prompt: str) -> dict:
        resp = self._gemini_model.generate_content(_ER16_PROMPT.format(prompt=prompt))
        return json.loads(resp.text)

    def _youtube_search(self, query: str):
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=self._youtube_api_key)
        return yt.search().list(
            q=query, part="id,snippet", type="video",
            maxResults=5, videoDuration="short",
        )

    def search_youtube(self, query: str) -> str:
        result = self._youtube_search(query).execute()
        return result["items"][0]["id"]["videoId"]

    def download_clip(self, video_id: str, dest_dir: Path) -> Path:
        url = f"https://www.youtube.com/watch?v={video_id}"
        out = dest_dir / f"{video_id}.mp4"
        subprocess.run(["yt-dlp", "-f", "mp4", "-o", str(out), url], check=True)
        return out

    def run_gvhmr(self, video_url: str) -> str:
        try:
            from scripts.gvhmr_modal_probe import process_video
            result = process_video.remote(video_url=video_url)
            return result.get("run_id", str(uuid.uuid4()))
        except Exception:
            return str(uuid.uuid4())
