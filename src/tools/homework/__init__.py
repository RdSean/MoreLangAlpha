"""Agent-facing homework tools.

The payload these tools return is a *contract*: its shape is declared in
``schemas.py``, exported to JSON Schema by
``scripts/contracts/export_schemas.py``, and consumed by the frontend as
generated zod. Change a model here and the frontend follows — but run the
exporter, because ``tests/unit/contracts`` fails until you do.
"""
