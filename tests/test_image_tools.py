import base64
import io
import json
import time
import unittest
from unittest.mock import patch

from companion.core import Answer, ReplyImage, Screenshot, UserError, ask, parse_answer
from companion.image_tools import ImageConnection
from test_reply_images import png


def response(provider, *, calls=None, text=None):
    calls = [] if calls is None else calls
    if provider == "OpenAI":
        return {"status": "completed", "output": [
            *([{"type": "message", "content": [{"type": "output_text", "text": text}]}] if text else []),
            *[{"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": str(i)}
              for i, (name, args) in enumerate(calls)]]}
    if provider == "Claude":
        return {"stop_reason": "tool_use" if calls else "end_turn", "content": [
            *([{"type": "text", "text": text}] if text else []),
            *[{"type": "tool_use", "name": name, "input": args, "id": str(i)} for i, (name, args) in enumerate(calls)]]}
    return {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [
        *([{"text": text}] if text else []),
        *[{"functionCall": {"name": name, "args": args}} for name, args in calls]]}}]}


class AutomaticImageTests(unittest.TestCase):
    def call(self, provider, data, **kwargs):
        requests = []
        def transport(request, **_):
            requests.append(request)
            return io.BytesIO(json.dumps(data).encode())
        answer = ask(provider, "chat-fixture", "test-model", "请画一张示意图", search=False,
                     transport=transport, **kwargs)
        self.assertEqual(len(requests), 1, "There must be no extra chat request or retry")
        return answer, json.loads(requests[0].data)

    def test_model_selects_image_tool_for_all_providers_and_key_stays_local(self):
        for provider in ("OpenAI", "Claude", "Gemini"):
            with self.subTest(provider=provider), patch("companion.image_tools.generate_image") as generate:
                generate.return_value = Answer("AI 示意图", images=[ReplyImage(png(), "示例", generated=True)])
                answer, body = self.call(provider, response(provider, calls=[("generate_illustration", {"prompt": "营地到树林的虚构示意图"})]),
                                         image_connection=ImageConnection("Gemini", "image-model", "image-fixture"))
                self.assertEqual(len(answer.images), 1)
                generate.assert_called_once()
                self.assertEqual(generate.call_args.args[:3], ("Gemini", "image-fixture", "image-model"))
                self.assertNotIn("image-fixture", json.dumps(body))
                self.assertIn("generate_illustration", json.dumps(body))
                self.assertEqual(generate.call_args.kwargs["history"][-1]["content"], "请画一张示意图")

    def test_text_and_source_images_render_without_generation_or_mode(self):
        for provider in ("OpenAI", "Claude", "Gemini"):
            with self.subTest(provider=provider), patch("companion.image_tools.generate_image") as generate:
                answer, _ = self.call(provider, response(provider, text="说明 ![来源图](https://example.org/image.png)"),
                                      image_connection=ImageConnection("OpenAI", "image-model", "fixture"))
                self.assertEqual(answer.text.strip(), "说明")
                self.assertEqual(answer.images[0].url, "https://example.org/image.png")
                generate.assert_not_called()

    def test_no_configuration_or_screenshot_does_not_offer_or_execute_tool(self):
        connection = ImageConnection("OpenAI", "image-model", "fixture")
        configurations = ({}, {"image_connection": ImageConnection("OpenAI", "image-model", "")},
                          {"image_connection": connection, "screenshot": Screenshot(png(), time.time(), "fixture")})
        for provider in ("OpenAI", "Claude", "Gemini"):
            for config in configurations:
                with self.subTest(provider=provider, screenshot="screenshot" in config), patch("companion.image_tools.generate_image") as generate:
                    answer, body = self.call(provider, response(provider, calls=[("generate_illustration", {"prompt": "图"})]), **config)
                    self.assertNotIn("tools", body)
                    self.assertEqual("No image was generated.", answer.text)
                    generate.assert_not_called()

    def test_invalid_multiple_or_incomplete_tool_calls_never_spend_on_images(self):
        valid = ("generate_illustration", {"prompt": "图"})
        for provider in ("OpenAI", "Claude", "Gemini"):
            cases = [[valid, valid], [("run_shell", {"prompt": "图"})],
                     [("generate_illustration", {"prompt": "图", "key": "untrusted"})],
                     [("generate_illustration", {"prompt": ""})], [("generate_illustration", {"prompt": "a" * 12001})]]
            partial = response(provider, calls=[valid])
            if provider == "OpenAI": partial["status"] = "incomplete"
            elif provider == "Claude": partial["stop_reason"] = "max_tokens"
            else: partial["candidates"][0]["finishReason"] = "MAX_TOKENS"
            for data in [*[response(provider, calls=calls) for calls in cases], partial]:
                with self.subTest(provider=provider), patch("companion.image_tools.generate_image") as generate:
                    answer, _ = self.call(provider, data, image_connection=ImageConnection("OpenAI", "image-model", "fixture"))
                    self.assertTrue(answer.warnings)
                    self.assertEqual(answer.images, [])
                    generate.assert_not_called()

    def test_image_failure_preserves_text_and_does_not_retry_or_fallback(self):
        with patch("companion.image_tools.generate_image", side_effect=UserError("图片服务不可用")) as generate:
            answer, _ = self.call("Claude", response("Claude", text="示意说明", calls=[("generate_illustration", {"prompt": "图"})]),
                                  image_connection=ImageConnection("OpenAI", "image-model", "fixture"))
            self.assertEqual(answer.text, "示意说明")
            self.assertTrue(any("图片服务不可用" in x for x in answer.warnings))
            generate.assert_called_once()

    def test_native_image_only_answers_render_and_thought_images_are_hidden(self):
        b64 = base64.b64encode(png()).decode()
        result = parse_answer("OpenAI", {"status": "completed", "output": [
            {"type": "image_generation_call", "status": "completed", "result": b64}]})
        self.assertEqual(result.text, "")
        self.assertTrue(result.images[0].generated)
        result = parse_answer("Gemini", {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"thought": True, "inlineData": {"mimeType": "image/png", "data": "hidden"}},
            {"inlineData": {"mimeType": "image/png", "data": b64}}]}}]})
        self.assertEqual(len(result.images), 1)
        self.assertTrue(result.images[0].generated)
