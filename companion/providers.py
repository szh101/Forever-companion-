"""Curated API model choices, verified against official catalogs on 2026-10-11.

These are suggestions, not an assertion that a user's account has access.
The editable model dropdown also accepts other API model IDs.
"""

DEMO_PROVIDER = "演示（不联网）"
MODEL_CHOICES = {
    "OpenAI": (
        ("gpt-6.1-sol", "GPT-6.1 Sol · 均衡"),
        ("gpt-6-luna", "GPT-6 Luna · 经济"),
        ("gpt-6-astra", "GPT-6 Astra · 复杂推理"),
    ),
    "Gemini": (
        ("gemini-3.8-flash", "Gemini 3.8 Flash · 日常使用"),
        ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite · 经济"),
        ("gemini-3.1-pro-preview", "Gemini 3.1 Pro · 预览版"),
    ),
    "Claude": (
        ("claude-sonnet-5-5", "Claude Sonnet 5.5 · 均衡"),
        ("claude-haiku-5-5", "Claude Haiku 5.5 · 经济"),
        ("claude-opus-5-5", "Claude Opus 5.5 · 复杂推理"),
    ),
}
# Gemini grounding requires its accompanying Search Suggestions UI. This Tk
# client does not implement that presentation yet, so it never requests it.
WEB_SEARCH_PROVIDERS = frozenset(("OpenAI", "Claude"))


def model_hint(provider: str, model: str) -> str:
    if provider == DEMO_PROVIDER:
        return "离线演示无需模型或密钥。选择服务商后显示可选模型。"
    label = dict(MODEL_CHOICES.get(provider, ())).get(model.strip(), "自定义模型")
    return label + "\n也可直接输入其他模型 ID；可用性以你的 API 账号为准。"
