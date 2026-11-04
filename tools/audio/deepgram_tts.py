"""Deepgram Aura + Flux text-to-speech provider tool.

Flux TTS uses /v2/speak (e.g. model=flux-haley-en). Aura/Aura-2 uses /v1/speak.
Endpoint is auto-selected from model prefix.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class DeepgramTTS(BaseTool):
    name = "deepgram_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "deepgram"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set the DEEPGRAM_API_KEY environment variable:\n"
        "  export DEEPGRAM_API_KEY=your_key_here\n"
        "Get a key at https://console.deepgram.com/"
    )
    fallback = "piper_tts"
    fallback_tools = ["elevenlabs_tts", "openai_tts", "piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = ["text_to_speech", "voice_selection", "multilingual"]
    supports = {"voice_cloning": False, "multilingual": True, "offline": False, "native_audio": True}
    best_for = ["conversation-native Flux TTS (expressive, turn-aware)", "low-latency Aura narration", "cost-effective TTS via Deepgram"]
    not_good_for = ["fully offline production", "voice clone matching"]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "model": {
                "type": "string",
                "default": "flux-haley-en",
                "description": "Voice model: Flux TTS (flux-haley-en, 36 voices) via /v2/speak, or Aura (aura-2-thalia-en, aura-asteria-en) via /v1/speak",
            },
            "voice": {
                "type": "string",
                "description": "Alias for model. Use either voice or model.",
            },
            "encoding": {
                "type": "string",
                "default": "mp3",
                "enum": ["mp3", "linear16", "mulaw", "alaw", "opus", "flac", "aac"],
                "description": "Audio encoding",
            },
            "container": {"type": "string", "description": "Container override (e.g. none for raw mulaw)"},
            "sample_rate": {"type": "integer", "description": "Sample rate (e.g. 8000, 16000, 24000, 48000)"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True)
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["text", "model", "voice", "encoding"]
    side_effects = ["writes audio file to output_path", "calls Deepgram API"]
    user_visible_verification = ["Listen to generated audio for natural speech quality"]

    def get_status(self) -> ToolStatus:
        if os.environ.get("DEEPGRAM_API_KEY"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return round(len(inputs.get("text", "")) * 0.000015, 4)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            return ToolResult(success=False, error="No Deepgram API key. " + self.install_instructions)
        start = time.time()
        try:
            result = self._generate(inputs, api_key)
        except Exception as exc:
            safe = str(exc).replace(api_key, "[REDACTED]")
            return ToolResult(success=False, error=f"Deepgram TTS failed: {safe}")
        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any], api_key: str) -> ToolResult:
        import requests

        text = inputs["text"]
        model = inputs.get("voice") or inputs.get("model", "flux-haley-en")
        encoding = inputs.get("encoding", "mp3")
        container = inputs.get("container")
        sample_rate = inputs.get("sample_rate")

        is_flux = str(model).startswith("flux-")
        params: dict[str, Any] = {"model": model, "encoding": encoding}
        if container:
            params["container"] = container
        if sample_rate:
            params["sample_rate"] = sample_rate

        # ponytail: single REST call, no streaming/chunking; add if long-form >10k chars matters
        # Flux TTS requires /v2/speak; Aura uses /v1/speak
        url = "https://api.deepgram.com/v2/speak" if is_flux else "https://api.deepgram.com/v1/speak"
        resp = requests.post(
            url,
            params=params,
            headers={"Authorization": f"Token {api_key}", "Content-Type": "application/json"},
            json={"text": text},
            timeout=120,
        )
        resp.raise_for_status()

        # content-type may be audio/* or JSON error already handled by raise_for_status
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            # Deepgram sometimes returns JSON with audio URL - handle fallback
            try:
                j = resp.json()
                if "url" in str(j):
                    raise RuntimeError(f"Unexpected JSON response: {j}")
            except Exception:
                pass

        ext_map = {"mp3": "mp3", "linear16": "wav", "mulaw": "wav", "alaw": "wav", "opus": "ogg", "flac": "flac", "aac": "aac"}
        ext = ext_map.get(encoding, "mp3")
        output_path = Path(inputs.get("output_path", f"deepgram_tts.{ext}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)

        return ToolResult(
            success=True,
            data={"provider": self.provider, "model": model, "encoding": encoding, "text_length": len(text), "output": str(output_path)},
            artifacts=[str(output_path)],
            model=model,
        )
