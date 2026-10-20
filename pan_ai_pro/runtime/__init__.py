# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The runtime: Pydantic AI inside Odoo. Records in, an `Agent` out, runs in
slices on the workers, events over the bus. Imported lazily by the models so
a database without the Python dependency still loads the registry and says
why on the first run."""
