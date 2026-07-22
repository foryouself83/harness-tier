# CHANGELOG

<!-- version list -->

## v0.1.11-rc.1 (2026-07-22)

### Bug Fixes

- **skills**: Rust-cratesio token out of argv
  ([`86a92e5`](https://github.com/foryouself83/harness-tier/commit/86a92e58eba52fed0b2ac41fd565bd2c7661fa71))


## v0.1.10-rc.1 (2026-07-22)

### Bug Fixes

- **github**: Keep context values out of run blocks
  ([`1fe6c75`](https://github.com/foryouself83/harness-tier/commit/1fe6c75f33c12e7442cf50d14ce3f18c99a2b1d1))

- **skills**: Drop dead frontmatter, fix stale refs
  ([`3f171bd`](https://github.com/foryouself83/harness-tier/commit/3f171bd93b1839898a099e2063054656b5abb63b))

- **skills**: Test skill invocation against a measured baseline
  ([`5311332`](https://github.com/foryouself83/harness-tier/commit/5311332e3c929bc28ff73837e49a98a0bba04536))

### Features

- **flow**: Gate git merge on the strategy table
  ([`8340fc4`](https://github.com/foryouself83/harness-tier/commit/8340fc4768fdb9eeebb4707c9d56b06b0940530d))


## v0.1.9-rc.1 (2026-07-16)

### Features

- **authoring**: Add code-style quality lenses
  ([`ac558e0`](https://github.com/foryouself83/harness-tier/commit/ac558e05deb5caeecf08b71ae5c2700ff5f71a42))

- **authoring**: No plan indices in code comments
  ([`5dfb24d`](https://github.com/foryouself83/harness-tier/commit/5dfb24d108d72ccf02d156b7d8083469e8784588))

- **flow**: Per-check timing for custom module gates
  ([`1a47528`](https://github.com/foryouself83/harness-tier/commit/1a47528b4964ca1fa2acb17758574436f513ee02))

- **harness-init**: Incremental lens gap-fill
  ([`d82f340`](https://github.com/foryouself83/harness-tier/commit/d82f3401bdbaae56cbe194cb0b154cf4027ada24))


## v0.1.8-rc.1 (2026-07-13)

### Documentation

- **deploy**: Add /harness-deployments to README
  ([`12ae549`](https://github.com/foryouself83/harness-tier/commit/12ae5491219ce17c3aba3247597ddd8abe002f0d))

### Features

- **authoring**: SRS/SDS requirement traceability
  ([`1503c20`](https://github.com/foryouself83/harness-tier/commit/1503c20b52174ba05d19db7d91e3c28eae0d63cb))

- **deploy**: Harness-deployments deployment layer
  ([`a3b1863`](https://github.com/foryouself83/harness-tier/commit/a3b1863534f321008f4c1f19b2e6150e6ccb6498))

- **flow**: Rework commit discipline, drop no-PR
  ([`7bfa6c0`](https://github.com/foryouself83/harness-tier/commit/7bfa6c0481fcd3ec44e73733318e220b29a6b3e6))


## v0.1.7-rc.1 (2026-07-09)

### Bug Fixes

- **flow**: Add post-release back-merge step to promotion flow
  ([`86731b6`](https://github.com/foryouself83/harness-tier/commit/86731b62d8efa331ddbf2fc0c73355c9172ed873))

- **flow-init**: Wire pre-commit hygiene stage
  ([`ce1a6a5`](https://github.com/foryouself83/harness-tier/commit/ce1a6a57e845e5139b8f341c3c829a4d297a4f5b))

### Documentation

- Rework README/USAGE benefits and layer model
  ([`fc6a0a3`](https://github.com/foryouself83/harness-tier/commit/fc6a0a3fcf5b695e584fc813520aed6d2ac591d7))


## v0.1.6-rc.1 (2026-07-09)

### Bug Fixes

- **flow**: Enforce risk-tiers Merge strategy at merge time
  ([`118a9d4`](https://github.com/foryouself83/harness-tier/commit/118a9d494cec95dd6fba0cb1abec4751cce2fb96))

- **flow-init**: Fall back to default when timeout_minutes is null
  ([`4cdef52`](https://github.com/foryouself83/harness-tier/commit/4cdef5280ef3a20e8d43ad7e9c6574f10e3ffe60))

### Features

- **ci**: Unit-test CI workflow + tighten Action timeouts
  ([`718e670`](https://github.com/foryouself83/harness-tier/commit/718e670dbbf574a137de864c57b173dda0125e62))

- **flow**: Worktree-aware commit gate (branch-key)
  ([`b4fe12f`](https://github.com/foryouself83/harness-tier/commit/b4fe12f2673e0cd790830ab1baad18d7a5046d2f))


## v0.1.5-rc.1 (2026-07-06)

### Bug Fixes

- **performance,integration**: Fix 16 confirmed bugs, split static-checks.md by stack, promote
  Electron to a first-class branch
  ([`6298a1f`](https://github.com/foryouself83/harness-tier/commit/6298a1f1decd93e0140e495d4f0e4ad5b5b74072))

### Features

- **harness-init,flow-init**: Add C++/C#/Java/Kotlin/Rust/PHP/Ruby/Swift support
  ([`6b881da`](https://github.com/foryouself83/harness-tier/commit/6b881da0d163c65e12d890198d8afe0338dee416))


## v0.1.4-rc.1 (2026-07-05)

### Bug Fixes

- Harden harness-init fan-out/fan-in boundary
  ([`304df64`](https://github.com/foryouself83/harness-tier/commit/304df64980f5732f8e2c06df87cb5d9952e24fa5))


## v0.1.3-rc.1 (2026-07-03)

### Bug Fixes

- De-duplicate rule docs and guard authoring
  ([`30ac9f5`](https://github.com/foryouself83/harness-tier/commit/30ac9f5f51ec69c2ae23c064278f95fc0daa322c))

- Warn to merge post-rc origin/staging on release promotion
  ([`e6a3690`](https://github.com/foryouself83/harness-tier/commit/e6a3690ebb28a93d76ff50a49f86fc3d842957f3))

### Documentation

- Relabel commands as skills, drop check-deps
  ([`24fa033`](https://github.com/foryouself83/harness-tier/commit/24fa033c59bb254bf3c346fd51b0f857f8934c34))

### Features

- Release templates fall back to GITHUB_TOKEN
  ([`a45ac5a`](https://github.com/foryouself83/harness-tier/commit/a45ac5a97e10b9cca3621ed3c3b8ae255c4a8fca))


## v0.1.2-rc.1 (2026-07-02)

### Documentation

- Design grouped release notes (mechanical)
  ([`0f8b8d8`](https://github.com/foryouself83/harness-tier/commit/0f8b8d8c9b18d77afba0928cbb346ba6a61efdb4))

### Features

- Grouped changelog as GitHub Release body
  ([`72ed297`](https://github.com/foryouself83/harness-tier/commit/72ed29797384507db8e7fdcdd37d82b50b19d32a))


## v0.1.1-rc.1 (2026-07-02)

### Documentation

- Bump-gate spec/plan + token-permission guide
  ([`74e88c2`](https://github.com/foryouself83/harness-tier/commit/74e88c2c13c7346c0baae98794612ac8700b2bc5))

### Features

- Staging bump-level gate + token-write guard
  ([`f79c66d`](https://github.com/foryouself83/harness-tier/commit/f79c66db9bc866bc811aad172e3666294ca882f8))
