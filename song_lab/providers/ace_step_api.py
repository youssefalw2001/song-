from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from song_lab.audio.jobs import SongJob, SongJobResult
from song_lab.providers.base import SongProvider


class AceStepApiError(RuntimeError):
    """Raised when the ACE-Step API returns an invalid or failed response."""


class AceStepApiProvider(SongProvider):
    """Provider for a local ACE-Step API server.

    Start ACE-Step separately, usually with:
        uv run acestep-api

    Default server:
        http://127.0.0.1:8001
    """

    name = "ace_step_api"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        poll_seconds: float = 2.0,
        timeout_seconds: int = 900,
        vocal_language: str = "ar",
        audio_format: str = "mp3",
        thinking: bool = True,
        use_format: bool = True,
    ) -> None:
        self.base_url = (base_url or os.getenv("ACESTEP_API_URL") or "http://127.0.0.1:8001").rstrip("/")
        self.api_key = api_key or os.getenv("ACESTEP_API_KEY")
        self.model = model or os.getenv("ACESTEP_MODEL") or "acestep-v15-turbo"
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.vocal_language = vocal_language
        self.audio_format = audio_format
        self.thinking = thinking
        self.use_format = use_format

    def run(self, job: SongJob) -> SongJobResult:
        job.output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = job.output_dir / self._metadata_name()

        try:
            task_id = self.release_task(job)
            task_result = self.wait_for_task(task_id)
            downloaded_path = self.download_first_audio(task_result, job.output_dir, task_id)

            metadata = {
                "provider": self.name,
                "task_id": task_id,
                "result": task_result,
                "downloaded_path": str(downloaded_path),
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            return SongJobResult(
                provider=self.name,
                status="generated",
                output_path=downloaded_path,
                metadata_path=metadata_path,
                message="ACE-Step generated audio successfully.",
            )
        except Exception as exc:
            metadata_path.write_text(
                json.dumps({"provider": self.name, "error": str(exc)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return SongJobResult(
                provider=self.name,
                status="failed",
                output_path=metadata_path,
                metadata_path=metadata_path,
                message=f"ACE-Step generation failed: {exc}",
            )

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def release_task(self, job: SongJob) -> str:
        payload: dict[str, Any] = {
            "prompt": job.prompt,
            "lyrics": job.lyrics or "",
            "audio_duration": job.duration_seconds,
            "audio_format": self.audio_format,
            "vocal_language": self.vocal_language,
            "thinking": self.thinking,
            "use_format": self.use_format,
            "model": self.model,
            "batch_size": 1,
        }

        if job.seed is not None:
            payload["use_random_seed"] = False
            payload["seed"] = job.seed

        response = self._request_json("POST", "/release_task", payload)
        data = self._unwrap(response)
        task_id = data.get("task_id")
        if not task_id:
            raise AceStepApiError(f"ACE-Step did not return task_id: {response}")
        return str(task_id)

    def wait_for_task(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds

        while time.monotonic() < deadline:
            response = self._request_json("POST", "/query_result", {"task_id_list": [task_id]})
            data = self._unwrap(response)
            if not isinstance(data, list) or not data:
                raise AceStepApiError(f"Invalid query_result response: {response}")

            item = data[0]
            status = int(item.get("status", 0))
            if status == 1:
                parsed = self._parse_result_json(item.get("result"))
                if not parsed:
                    raise AceStepApiError(f"Task succeeded but returned no result: {item}")
                return parsed[0]
            if status == 2:
                raise AceStepApiError(f"ACE-Step task failed: {item}")

            time.sleep(self.poll_seconds)

        raise TimeoutError(f"ACE-Step task timed out after {self.timeout_seconds} seconds: {task_id}")

    def download_first_audio(self, result: dict[str, Any], output_dir: Path, task_id: str) -> Path:
        file_url = result.get("file")
        if not file_url:
            raise AceStepApiError(f"Result missing audio file URL: {result}")

        if file_url.startswith("http://") or file_url.startswith("https://"):
            url = file_url
        else:
            url = f"{self.base_url}{file_url}"

        suffix = self.audio_format.lstrip(".") or "mp3"
        output_path = output_dir / f"ace-step-{task_id}.{suffix}"

        request = urllib.request.Request(url, headers=self._headers(include_json=False))
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())

        return output_path

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        headers = self._headers(include_json=True)

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.URLError as exc:
            raise AceStepApiError(f"Could not reach ACE-Step API at {url}: {exc}") from exc

    def _headers(self, include_json: bool) -> dict[str, str]:
        headers: dict[str, str] = {}
        if include_json:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _unwrap(response: dict[str, Any]) -> Any:
        if response.get("code") != 200:
            raise AceStepApiError(f"ACE-Step API error: {response}")
        return response.get("data")

    @staticmethod
    def _parse_result_json(raw_result: Any) -> list[dict[str, Any]]:
        if isinstance(raw_result, list):
            return raw_result
        if isinstance(raw_result, str):
            parsed = json.loads(raw_result)
            if isinstance(parsed, list):
                return parsed
        raise AceStepApiError(f"Cannot parse ACE-Step result JSON: {raw_result}")

    @staticmethod
    def _metadata_name() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"ace-step-run-{timestamp}.json"
