# Version Pinning (injection block)

- For any referenced **package, library, or container image**, do not use range/floating specifiers such as
  `>=`, `^`, `~`, or latest → **pin to an exact `==` (or a lockfile / digest)**.
- Examples: `fastapi==0.118.0`, `node:22.11.0-bookworm` (digest recommended),
  `react@19.0.0`. This guarantees reproducible builds.
- Perform upgrades as deliberate, individual changes (do not let them drift in via floating updates).
