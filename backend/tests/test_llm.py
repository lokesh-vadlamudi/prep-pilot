from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app import llm
from app.config import settings


class LlmTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_uses_vllm_openai_compatible_endpoint_and_payload(self):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "  grounded answer  "}}]}
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        old_base_url = settings.llm_base_url
        settings.llm_base_url = "http://dgx.test:8000/v1/"
        try:
            with patch("app.llm.httpx.AsyncClient", return_value=context):
                answer = await llm.chat([{"role": "user", "content": "Question"}], temperature=0.2, num_predict=321)
        finally:
            settings.llm_base_url = old_base_url

        self.assertEqual(answer, "grounded answer")
        response.raise_for_status.assert_called_once_with()
        client.post.assert_awaited_once()
        url, = client.post.await_args.args
        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(url, "http://dgx.test:8000/v1/chat/completions")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 321)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("think", payload)
        self.assertNotIn("options", payload)

    async def test_chat_rejects_empty_vllm_choices(self):
        response = MagicMock()
        response.json.return_value = {"choices": []}
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("app.llm.httpx.AsyncClient", return_value=context):
            with self.assertRaisesRegex(llm.LLMError, "no completion choices"):
                await llm.chat([{"role": "user", "content": "Question"}])

    async def test_health_uses_vllm_models_endpoint(self):
        response = MagicMock(status_code=200)
        client = AsyncMock()
        client.get.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        old_base_url = settings.llm_base_url
        settings.llm_base_url = "http://dgx.test:8000/v1/"
        try:
            with patch("app.llm.httpx.AsyncClient", return_value=context):
                self.assertTrue(await llm.health())
        finally:
            settings.llm_base_url = old_base_url

        client.get.assert_awaited_once_with("http://dgx.test:8000/v1/models")


if __name__ == "__main__":
    unittest.main()
