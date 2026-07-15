# -*- coding: utf-8 -*-
import logging

from odoo.addons.ai.utils.llm_providers import PROVIDERS, Provider

_logger = logging.getLogger(__name__)

# Register Anthropic as a provider.
# Anthropic does not have an embedding API, so we leave embedding_model empty.
# RAG sources on Claude agents will fall back to another provider's embedding model.
_provider_fields = {
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
}

# Build against whatever fields this Odoo's Provider actually declares.
# A July 2026 enterprise update added a required `deprecated_models` field;
# this module runs on instances both before and after it, and getting it
# wrong either way is a TypeError at import — which fails the module, fails
# the registry, and takes the whole database down with it. So ask the
# NamedTuple instead of assuming, and never pass a field it doesn't declare.
if "deprecated_models" in Provider._fields:
    _provider_fields["deprecated_models"] = []

PROVIDERS.append(Provider(**_provider_fields))

_logger.info("[AI Pro] Registered Anthropic provider with %d models", 3)
