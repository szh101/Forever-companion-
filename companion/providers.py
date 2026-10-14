"""Curated API model choices, verified against official catalogs on 2026-10-11.

These are suggestions, not an assertion that a user's account has access.
The editable model dropdown also accepts other API model IDs.
"""

DEMO_PROVIDER = "Offline demo"
MODEL_CHOICES = {
    "OpenAI": (
        ("gpt-6.1-sol", "GPT-6.1 Sol · Balanced"),
        ("gpt-6-luna", "GPT-6 Luna · Budget"),
        ("gpt-6-astra", "GPT-6 Astra · Advanced reasoning"),
    ),
    "Gemini": (
        ("gemini-3.8-flash", "Gemini 3.8 Flash · Everyday use"),
        ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite · Budget"),
        ("gemini-3.1-pro-preview", "Gemini 3.1 Pro · Preview"),
    ),
    "Claude": (
        ("claude-sonnet-5-5", "Claude Sonnet 5.5 · Balanced"),
        ("claude-haiku-5-5", "Claude Haiku 5.5 · Budget"),
        ("claude-opus-5-5", "Claude Opus 5.5 · Advanced reasoning"),
    ),
}
# Gemini grounding requires its accompanying Search Suggestions UI. This Tk
# client does not implement that presentation yet, so it never requests it.
WEB_SEARCH_PROVIDERS = frozenset(("OpenAI", "Claude"))


def model_hint(provider: str, model: str) -> str:
    if provider == DEMO_PROVIDER:
        return "Offline demo needs no model or key. Select a provider to see available model choices."
    label = dict(MODEL_CHOICES.get(provider, ())).get(model.strip(), "Custom model")
    return label + "\nYou can also enter another model ID. Availability depends on your API account."
