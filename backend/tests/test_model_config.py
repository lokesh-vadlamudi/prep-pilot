"""Regression coverage for the DGX model ID sent to vLLM."""
from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app import llm
from app.config import Settings

SERVED_MODEL_ID = "qwen3.8-27b"


def settings_defaults_only() -> Settings:
    """Build settings without `.env` or process-environment overrides."""
    saved = {key: os.environ.pop(key) for key in ("MODEL", "LLM_BASE_URL") if key in os.environ}
    try:
        return Settings(_env_file=None)
    finally:
        os.environ.update(saved)


class ModelConfigTests(unittest.TestCase):
    def test_default_model_is_exact_served_model_id(self):
        self.assertEqual(settings_defaults_only().model, SERVED_MODEL_ID)

    def test_model_environment_variable_overrides_default(self):
        with patch.dict(os.environ, {"MODEL": "env-override"}, clear=False):
            self.assertEqual(Settings(_env_file=None).model, "env-override")


class ChatPayloadModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_sends_configured_model_id(self):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("app.llm.httpx.AsyncClient", return_value=context):
            await llm.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(client.post.await_args.kwargs["json"]["model"], SERVED_MODEL_ID)
