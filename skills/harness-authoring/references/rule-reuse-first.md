### Reuse / Off-the-Shelf First (reuse-before-build)

Before implementing code yourself, first search for and recommend an off-the-shelf solution that is **free and permitted for commercial use**.

**Search scope (tool-based)**: official Docker images, standard libraries, framework built-ins,
and well-maintained OSS from package registries (Docker Hub, PyPI, npm, etc.).

**Cost / license gate**: For each candidate, verify its cost (free?), license (commercial use allowed?), and maintenance status, and
**do not recommend paid solutions (paid managed services, paid licenses, SaaS subscriptions).**
If there is no free, commercially usable candidate, or none fits the requirements, implement it yourself.
Mark uncertain licenses/costs as "needs verification" rather than asserting them (no making things up).

**Why**: Building it yourself takes on new maintenance, security, and edge-case burdens. Free OSS off-the-shelf options
externalize that burden while carrying no cost or license constraints. That said, this does not block legitimate domain-specific implementations.
