# Karpathy CLAUDE.md Principles (injection block)

> When implementing, fetch the actual source and refresh with its latest wording (do not guess). Source: Forrest Chang's
> `andrej-karpathy-skills` (a distillation of Karpathy's observations on LLM coding). Below is the gist of the four verified principles.

1. **Think Before Coding** — State your assumptions, and when something is ambiguous, ask instead of guessing.
   When multiple interpretations are possible, present them rather than picking one arbitrarily. If a simpler path exists, push back.
2. **Simplicity First** — Only what was asked, with minimal code. No unrequested abstractions, features, configuration, or
   over-defensive code. Don't write in 200 lines what fits in 50.
3. **Surgical Changes** — Every line you change must be directly tied to the request. Touch only what needs touching,
   and clean up only what you created.
4. **Goal-Driven Execution** — Turn the instruction into verifiable success criteria. For multi-step work, first draft a
   short plan with verification checkpoints.
