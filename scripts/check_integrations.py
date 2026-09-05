"""Report briefing and sponsor wiring without printing secrets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mandate.env import load_runtime_env, masked
from mandate.money_operations_audio import audio_configured, audio_enabled

path = load_runtime_env()
print(f'dotenv: {"loaded " + str(path) if path else "not present (using process env)"}')
print(f'elevenlabs_enabled: {audio_enabled()}')
print(f'elevenlabs_key: {masked("ELEVENLABS_API_KEY")}')
print(f'elevenlabs_voice: {masked("ELEVENLABS_VOICE_ID")}')
print(f'elevenlabs_ready: {audio_enabled() and audio_configured()}')
print(f'model_url: {masked("MANDATE_MODEL_URL")}')
print(f'model_key: {masked("MANDATE_MODEL_KEY")}')
print(f'model_name: {os.getenv("MANDATE_MODEL_NAME") or "missing"}')
print(f'synthetic_egress: {os.getenv("MANDATE_ALLOW_SYNTHETIC_EGRESS") == "1"}')
print(f'prism_key: {masked("PRISMTRACE_API_KEY")}')
print(f'prism_project: {masked("PRISMTRACE_PROJECT_ID")}')
print('Voice and chat never approve. Controller review is required first.')
