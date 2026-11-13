# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Keep fastmcp off the working directory's `.env`.

`import pydantic_ai` imports fastmcp, whose settings read `.env` from the
current directory at import time. A process started from a folder holding an
`.env` it may not read (Cloudpepper's "Login as" runs from one) then fails to
load this module with PermissionError. Nothing of ours is configured through
that file, so fastmcp gets an empty one, unless someone set it explicitly.
Imported first from `__init__`, before anything imports pydantic_ai.
"""

import os

os.environ.setdefault("FASTMCP_ENV_FILE", os.devnull)
