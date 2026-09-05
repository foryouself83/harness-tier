"""Behavior spec for the shared helper _harness_paths — path SSOT, fallback helpers,
encoding defenses.

If this module breaks, path resolution in every gate script breaks along with it, so the
consolidated behavior is pinned here in one place (rather than each script carrying its own
host_root/force_utf8_io and tested it separately).
"""
