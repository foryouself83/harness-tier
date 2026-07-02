# Baseline Security (injection block)

- **Never put secrets, keys, tokens, or passwords in code or commits.** Separate them out via `.env` or a secrets manager,
  and keep `.env` and credential files in `.gitignore`.
- **Do not trust** user input — validate and escape it at the boundary (injection / XSS / path traversal).
- Do not leave debug or permissive defaults (`debug=true`, `CORS *`, wildcard permissions) in production.
- Keep dependencies off known-vulnerable versions (§Version Pinning) and put a security scanner in CI (opt-in).
