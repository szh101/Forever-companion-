import io
import json
import time
import unittest
import urllib.error

from companion.core import (MAX_RESPONSE, NoRedirect, Screenshot, UserError, ask,
                            build_request, parse_answer, parse_snapshot, snapshot_status)
from companion.providers import MODEL_CHOICES


def snapshot():
    return {"kind": "forever-ai-snapshot", "schemaVersion": 1, "capturedAt": int(time.time()),
            "client": {"version": "test"}, "player": {"level": 12},
            "quests": [{"id": 123, "title": "测试任务（非游戏资料）"}]}


class CoreTests(unittest.TestCase):
    def test_snapshot_validation_and_staleness(self):
        data = parse_snapshot(json.dumps(snapshot()))
        self.assertIn("1 quest", snapshot_status(data))
        self.assertIn("Outdated", snapshot_status(data, data["capturedAt"] + 301))
        for invalid in ["return {}", "[]", "{}", json.dumps({**data, "capturedAt": True}),
                        json.dumps({**data, "quests": ["wrong"]}),
                        json.dumps({**data, "quests": [{"id": True, "title": "x"}]}), "x" * 200001]:
            with self.subTest(invalid=invalid[:40]), self.assertRaises(UserError):
                parse_snapshot(invalid)

    def test_openai_contract_vision_context_and_search(self):
        shot = Screenshot(b"\x89PNG\r\n\x1a\nfixture", time.time(), "test")
        url, body = build_request("OpenAI", "user-model", "配方在哪里？", snapshot=snapshot(), screenshot=shot)
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertFalse(body["store"])
        self.assertEqual(body["tools"], [{"type": "web_search"}])
        self.assertIn("UNTRUSTED GAME SNAPSHOT", body["input"][-1]["content"][0]["text"])
        self.assertEqual(body["input"][-1]["content"][1]["type"], "input_image")
        self.assertIn("not Classic Era", body["instructions"])

    def test_claude_contract_and_history_bound(self):
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(20)]
        url, body = build_request("Claude", "my-claude", "任务排序", history=history,
                                 screenshot=Screenshot(b"\x89PNG\r\n\x1a\nfixture", time.time(), "test"))
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(len(body["messages"]), 9)
        self.assertEqual(body["messages"][0]["content"], "12")
        self.assertEqual(body["tools"][0]["type"], "web_search_20250305")
        self.assertEqual(body["messages"][-1]["content"][1]["source"]["media_type"], "image/png")
        self.assertNotIn("tools", build_request("Claude", "my-claude", "x", search=False)[1])

    def test_model_presets_build_requests_for_their_provider(self):
        for provider, choices in MODEL_CHOICES.items():
            for model, _ in choices:
                with self.subTest(provider=provider, model=model):
                    url, body = build_request(provider, model, "如何安排任务？")
                    self.assertTrue(url.startswith("https://"))
                    self.assertTrue(body)

    def test_gemini_contract_image_history_and_fixed_endpoint(self):
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(20)]
        url, body = build_request("Gemini", "gemini-3.8-flash", "分析任务", history=history,
                                 snapshot=snapshot(),
                                 screenshot=Screenshot(b"\x89PNG\r\n\x1a\nfixture", time.time(), "test"))
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent")
        self.assertEqual(len(body["contents"]), 9)
        self.assertEqual(body["contents"][0], {"role": "user", "parts": [{"text": "12"}]})
        self.assertEqual(body["contents"][1]["role"], "model")
        self.assertIn("UNTRUSTED GAME SNAPSHOT", body["contents"][-1]["parts"][0]["text"])
        self.assertIn("Web search enabled: False", body["contents"][-1]["parts"][0]["text"])
        self.assertEqual(body["contents"][-1]["parts"][1]["inlineData"]["mimeType"], "image/png")
        self.assertIn("not Classic Era", body["systemInstruction"]["parts"][0]["text"])
        self.assertNotIn("tools", body)

    def test_gemini_rejects_url_manipulation_and_unsupported_search(self):
        for model in ("../models/x", "x?key=other", "x#fragment", "x%2Fother", "https://example.org", "models/x"):
            with self.subTest(model=model), self.assertRaises(UserError):
                build_request("Gemini", model, "x")
        with self.assertRaisesRegex(UserError, "does not support web search"):
            ask("Gemini", "fixture", "gemini-3.8-flash", "x", search=True,
                transport=lambda *a, **kw: self.fail("Must reject before network access"))

    def test_gemini_response_and_headers_without_exposing_key_or_thought(self):
        requests = []
        response = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [
            {"thought": True, "text": "private thinking"}, {"text": "先交已完成任务。"}]},
            "citationMetadata": {"citationSources": [{"uri": "https://example.org/ungrounded"}]}}],
            "usageMetadata": {"totalTokenCount": 32}}

        def transport(req, timeout):
            requests.append(req)
            return io.BytesIO(json.dumps(response).encode())

        answer = ask("Gemini", "fixture-secret", "gemini-3.8-flash", "x", transport=transport)
        self.assertEqual(answer.text, "先交已完成任务。")
        self.assertEqual(answer.usage["totalTokenCount"], 32)
        self.assertEqual(answer.sources, [])
        self.assertTrue(any("output limit" in text for text in answer.warnings))
        self.assertTrue(any("did not search the web" in text for text in answer.warnings))
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].get_header("X-goog-api-key"), "fixture-secret")
        self.assertIsNone(requests[0].get_header("Authorization"))
        self.assertNotIn("fixture-secret", requests[0].full_url)
        self.assertNotIn(b"fixture-secret", requests[0].data)

    def test_gemini_blocked_empty_and_thought_only_responses(self):
        cases = [
            {"promptFeedback": {"blockReason": "SAFETY"}},
            {"candidates": []},
            {"candidates": [{"finishReason": "SAFETY", "content": {"parts": [{"text": "partial"}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"thought": True, "text": "hidden"}]}}]},
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(UserError):
                parse_answer("Gemini", data)

    def test_invalid_models_and_expired_images_fail_before_network(self):
        for provider, model, prompt in [("other", "x", "x"), ("OpenAI", "", "x"),
                                        ("Claude", "model with spaces", "x"), ("OpenAI", "x", "")]:
            with self.assertRaises(UserError):
                build_request(provider, model, prompt)
        with self.assertRaises(UserError):
            build_request("OpenAI", "m", "p", screenshot=Screenshot(b"\x89PNG\r\n\x1a\n", time.time() - 130, "old"))

    def test_citations_are_not_model_text_links(self):
        result = parse_answer("OpenAI", {"status": "completed", "output": [{"content": [{"type": "output_text",
            "text": "Example answer", "annotations": [
                {"type": "url_citation", "title": "source", "url": "https://example.org/item"},
                {"type": "url_citation", "title": "unsafe", "url": "javascript:alert(1)"},
                {"type": "url_citation", "title": "unsafe", "url": "https://name:password@example.org"}]}]}]})
        self.assertEqual(result.sources, [("source", "https://example.org/item")])
        self.assertEqual(result.warnings, [])

    def test_missing_search_results_and_partial_answer_are_visible(self):
        result = parse_answer("Claude", {"stop_reason": "max_tokens", "content": [
            {"type": "web_search_tool_result", "content": {"type": "web_search_tool_result_error"}},
            {"type": "text", "text": "unverified"}]})
        self.assertEqual(len(result.warnings), 3)
        with self.assertRaises(UserError):
            parse_answer("OpenAI", {"output": []})

    def test_http_headers_redaction_and_no_automatic_retry(self):
        requests = []

        def transport(req, timeout):
            requests.append(req)
            return io.BytesIO(json.dumps({"content": [{"type": "text", "text": "ok", "citations": [
                {"type": "web_search_result_location", "title": "test", "url": "https://example.org"}]}]}).encode())

        self.assertEqual(ask("Claude", "test-secret", "m", "p", transport=transport).text, "ok")
        self.assertEqual(requests[0].get_header("X-api-key"), "test-secret")
        self.assertNotIn(b"test-secret", requests[0].data)
        count = []

        def failed(req, timeout):
            count.append(1)
            raise urllib.error.HTTPError(req.full_url, 400, "test-secret", {}, io.BytesIO(b"test-secret"))

        with self.assertRaises(UserError) as caught:
            ask("OpenAI", "test-secret", "m", "p", transport=failed)
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertEqual(len(count), 1)

    def test_redirect_and_oversized_response_blocked(self):
        with self.assertRaises(UserError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://wrong.example")
        with self.assertRaises(UserError):
            ask("OpenAI", "fixture", "m", "p", transport=lambda *a, **kw: io.BytesIO(b"x" * (MAX_RESPONSE + 1)))


if __name__ == "__main__":
    unittest.main()
