"""The model-free half of the eval harness.

Measuring spends hours of rate-limit budget; checking spends nothing. Keeping the check
here means `uv run pytest` and `unit-test.yml` both enforce it with no new wiring.
"""
