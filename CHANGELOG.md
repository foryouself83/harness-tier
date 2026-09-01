# CHANGELOG

<!-- version list -->

## v0.2.3-rc.4 (2026-09-01)

### Bug Fixes

- **gate**: Read the commands a shell actually runs
  ([`89fbab7`](https://github.com/foryouself83/harness-tier/commit/89fbab7d31a64d4ee6ca8336e436a3ca3c8f12fe))


## v0.2.3-rc.3 (2026-09-01)

### Bug Fixes

- **gate**: One authority for what a command is
  ([`ec32a56`](https://github.com/foryouself83/harness-tier/commit/ec32a562738fb31233fe2145c66d22ed816526b0))


## v0.2.3-rc.2 (2026-09-01)

### Bug Fixes

- **gate**: Agree on what a git invocation is
  ([`64919b5`](https://github.com/foryouself83/harness-tier/commit/64919b5fed8bcd3cddf0e16cdda1eb15e90a4c40))


## v0.2.3-rc.1 (2026-09-01)

### Bug Fixes

- **gate**: One quoting authority for both halves
  ([`dc15b70`](https://github.com/foryouself83/harness-tier/commit/dc15b7005c1507b7f5cf271f9c15e8fb423c01f0))

- **gate**: Read a command the way a shell would
  ([`4b920af`](https://github.com/foryouself83/harness-tier/commit/4b920afc7171cef4904e78e7544c3b042a6463cb))

- **release**: Exclude the one broken GitPython
  ([`d44c555`](https://github.com/foryouself83/harness-tier/commit/d44c555b57c9cd85fa0e6a32dc11e1a0e5e602fe))

### Features

- **hook**: Tell a consumer an update is waiting
  ([`e8870a3`](https://github.com/foryouself83/harness-tier/commit/e8870a30e3436e80a197f230f79b43cf75838267))


## v0.2.2-rc.1 (2026-08-28)

### Bug Fixes

- **commit**: Drop version files from guide scope
  ([`964f04f`](https://github.com/foryouself83/harness-tier/commit/964f04f79c33d0cf9b5a81af96af62a7dea555a2))

- **commit**: Let the issued commit reach the gate
  ([`024126c`](https://github.com/foryouself83/harness-tier/commit/024126c9d256cb84ffe3e91e93c2494b4d4d9d23))

- **commit**: State what the self-filter rejects
  ([`e3f7fec`](https://github.com/foryouself83/harness-tier/commit/e3f7feca7d08ac53bca0547b3a5f8e659596d5af))

- **release**: Pin GitPython under 3.1.60
  ([`cc608cd`](https://github.com/foryouself83/harness-tier/commit/cc608cde1ffbd7db9a496556962a83baa73d51ab))

- **release**: Stop pinning the cargo checkout ref
  ([`2182ab4`](https://github.com/foryouself83/harness-tier/commit/2182ab4f94bfecbce2fdd4473752541b9da1e6b3))

### Features

- **commit**: Route flow commits through a skill
  ([`8037698`](https://github.com/foryouself83/harness-tier/commit/80376986f15b15df96117c155db4ff36cd812efe))


## v0.2.1-rc.2 (2026-08-25)

### Bug Fixes

- Make the outcome fingerprint platform-stable
  ([`6bf4393`](https://github.com/foryouself83/harness-tier/commit/6bf4393037fe2f3e8a8f4ea1b41b0497f2c3874b))


## v0.2.1-rc.1 (2026-08-21)

### Bug Fixes

- Close the gaps found reviewing wiki hardening
  ([`ca824c5`](https://github.com/foryouself83/harness-tier/commit/ca824c530746a8fc9681f545094ecc3ed158bc76))

- **docs**: Narrow the uninstall breakage claim
  ([`eecfcdf`](https://github.com/foryouself83/harness-tier/commit/eecfcdf20b925ca82a56576e225dc088649713e0))


## v0.2.0-rc.1 (2026-08-20)

### Bug Fixes

- **flow**: Close five deferred coverage gaps
  ([`ee6ba4f`](https://github.com/foryouself83/harness-tier/commit/ee6ba4f4cd545a92db4dfaa54dcebe2df49000ba))

- **flow**: Make the step 2.7 tests portable
  ([`66b7463`](https://github.com/foryouself83/harness-tier/commit/66b7463b7c161e17f424348f94c0d89c81149b62))

- **flow-init**: Flag a miscased unit_test language
  ([`ed40ded`](https://github.com/foryouself83/harness-tier/commit/ed40dedb2fc44272e340261e3eb2c4ec1b0f2784))

### Documentation

- Drop a convention the scripts state
  ([`ca6d110`](https://github.com/foryouself83/harness-tier/commit/ca6d1103b4dfa99e2e1ff181760083819c29241d))

### Features

- **doc-sync**: Check sibling translation parity
  ([`a0d3915`](https://github.com/foryouself83/harness-tier/commit/a0d3915fcd2676c8b067c299ae9aaaec52fcbfb0))

- **rules**: Cut ceremony from authored prose
  ([`f7487e6`](https://github.com/foryouself83/harness-tier/commit/f7487e678a6749285b9c0f9becdc9de57703e54b))

- **wiki**: Add the LLM Wiki and its verify gate
  ([`fc24c5d`](https://github.com/foryouself83/harness-tier/commit/fc24c5d000ca63b78842fb126f11c6fc85e94ce8))

- **wiki**: Make wiki_id derivation executable
  ([`7687680`](https://github.com/foryouself83/harness-tier/commit/76876806ae78373da14f527d18b7aedfc32ea1c5))

- **wiki**: Open a read path and harden the gate
  ([`19fc296`](https://github.com/foryouself83/harness-tier/commit/19fc296232c94a8e4c6154b44f2f556c571e6c02))


## v0.1.13-rc.1 (2026-07-30)

### Bug Fixes

- **flow**: Check bypass actors on their own axis
  ([`4d35a73`](https://github.com/foryouself83/harness-tier/commit/4d35a734c9545604b16452a6af2fef6d09c8c663))

### Documentation

- Record the PR workflow design decisions
  ([`604bf0c`](https://github.com/foryouself83/harness-tier/commit/604bf0c6ff379472b67d63cce752ddd9d8da2f08))

### Features

- **flow**: Make PR workflow an init choice
  ([`d202cb3`](https://github.com/foryouself83/harness-tier/commit/d202cb3347a4b8c250b358d8d0dc484b99276082))

- **flow**: Make review-gate coverage verifiable
  ([`31c200b`](https://github.com/foryouself83/harness-tier/commit/31c200bb2f04a70cfcfb993c3ac84573b687899c))


## v0.1.12-rc.1 (2026-07-27)

### Bug Fixes

- **flow**: Target the root cause, not the symptom
  ([`7187dc1`](https://github.com/foryouself83/harness-tier/commit/7187dc164679a88ebc6cedb802f20eece6be1de8))

- **performance**: Broaden invocation triggers
  ([`1113f05`](https://github.com/foryouself83/harness-tier/commit/1113f057236effffbb087cce363b816e443ba460))

### Documentation

- Record outcome-probe finding — outcome eval viable via permission grant
  ([`7c36cec`](https://github.com/foryouself83/harness-tier/commit/7c36cecad3693a396cee85c2fa3efb2e5c2d7d44))

- Router outcome-probe spec, plan, and finding
  ([`02bd81b`](https://github.com/foryouself83/harness-tier/commit/02bd81b57d87dc1820f6ea569f294bff9ab0ad21))


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
