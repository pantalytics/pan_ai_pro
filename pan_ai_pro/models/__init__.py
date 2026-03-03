# -*- coding: utf-8 -*-
from . import llm_providers
from . import llm_api_service
from . import res_config_settings
from . import ai_agent
from . import ir_model_fields
from . import ai_field_metadata

try:
    from . import ai_fields_patch
except ImportError:
    pass  # ai_fields not installed, skip patch
