# -*- coding: utf-8 -*-
import logging

from odoo.addons.ai.utils.llm_providers import PROVIDERS, Provider

_logger = logging.getLogger(__name__)

# Register Anthropic as a provider.
# Anthropic does not have an embedding API, so we leave embedding_model empty.
# RAG sources on Claude agents will fall back to another provider's embedding model.
PROVIDERS.append(
    Provider(
        name="anthropic",
        display_name="Anthropic",
        embedding_model="",
        embedding_config={
            "max_batch_size": 0,
            "max_tokens_per_request": 0,
        },
        llms=[
            ("claude-opus-4-6", "Claude Opus 4.6"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
        ],
    )
)

_logger.info("[AI Pro] Registered Anthropic provider with %d models", 3)
