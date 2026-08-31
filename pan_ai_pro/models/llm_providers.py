# -*- coding: utf-8 -*-
import logging

from odoo.addons.ai.utils.llm_providers import PROVIDERS, Provider

_logger = logging.getLogger(__name__)

# Register Anthropic as a provider.
# Anthropic does not have an embedding API, so we leave embedding_model empty.
# RAG sources on Claude agents will fall back to another provider's embedding model.
_PROVIDER_VALUES = {
    "name": "anthropic",
    "display_name": "Anthropic",
    "embedding_model": "",
    "embedding_config": {
        "max_batch_size": 0,
        "max_tokens_per_request": 0,
    },
    "llms": [
        ("claude-opus-4-6", "Claude Opus 4.6"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ],
    # We deprecate nothing, so the replacement map below is never consulted
    # today. It is filled in anyway so the provider behaves like the built-in
    # ones the day we do retire a model.
    "deprecated_models": [],
    "response_style_to_llm_model_and_reasoning": {
        "analytical": ("claude-opus-4-6", "medium"),
        "balanced": ("claude-sonnet-4-6", "low"),
        "creative": ("claude-sonnet-4-6", "low"),
    },
}


def _blank_for(annotation):
    """A harmless empty value for a Provider field we have never heard of."""
    text = str(annotation).lower()
    if "dict" in text:
        return {}
    if "list" in text:
        return []
    if "str" in text:
        return ""
    return None


def _register_anthropic():
    # Odoo keeps adding required fields to this NamedTuple: `deprecated_models`
    # in July 2026, `response_style_to_llm_model_and_reasoning` in August. On
    # Odoo.sh the enterprise source updates on its own, so a hardcoded argument
    # list turns into a TypeError at import overnight -- which fails the module,
    # fails the registry, and takes the whole database down with it. Build from
    # the fields this Odoo declares instead of the ones we happen to know.
    values = {}
    for field in Provider._fields:
        if field in _PROVIDER_VALUES:
            values[field] = _PROVIDER_VALUES[field]
        elif field in Provider._field_defaults:
            values[field] = Provider._field_defaults[field]
        else:
            values[field] = _blank_for(Provider.__annotations__.get(field))
            _logger.warning(
                "[AI Pro] Provider gained an unknown field %r; passing an empty value", field
            )
    PROVIDERS.append(Provider(**values))
    _logger.info(
        "[AI Pro] Registered Anthropic provider with %d models", len(_PROVIDER_VALUES["llms"])
    )


try:
    _register_anthropic()
except Exception:
    # Never let this module be the reason a database refuses to load.
    _logger.exception("[AI Pro] Could not register the Anthropic provider; Claude models are unavailable")
