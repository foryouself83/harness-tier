# CHANGELOG

<!-- version list -->

## v0.4.4-rc.2 (2026-10-09)


## v0.4.4-rc.1 (2026-10-08)

### Bug Fixes

- **ci**: Let workflow templates pass real pushes
  ([`96f1701`](https://github.com/foryouself83/harness-tier/commit/96f1701aaafd33fbfc4b507b91b6389f70bed05d))

- **deploy**: Keep prereleases off stable channels
  ([`8411190`](https://github.com/foryouself83/harness-tier/commit/84111907a3fb15703db38a219610b200594a8013))

- **deps**: Name the Store python3 alias on Windows
  ([`ea9bb57`](https://github.com/foryouself83/harness-tier/commit/ea9bb579153b21c4bc977092ac06e267f9138d09))

- **doc-style**: Stop flagging ordinary documents
  ([`8874287`](https://github.com/foryouself83/harness-tier/commit/8874287ba7394465b119418e5fe4c10f7b3061a2))

- **docs**: State what the commit gate cannot read
  ([`2bd5b74`](https://github.com/foryouself83/harness-tier/commit/2bd5b74aa5105227b8ebfa910119869de6e65b35))

- **flow**: Write worktree markers where gate reads
  ([`a5bbb9e`](https://github.com/foryouself83/harness-tier/commit/a5bbb9e6a0b479adb231bdc81ddae7d60f998fe5))

- **flow-init**: Keep host files safe and runnable
  ([`f9af870`](https://github.com/foryouself83/harness-tier/commit/f9af87021143a466c98dd5485ba8eb55e7dae3e0))

- **flow-init**: Never write through host symlinks
  ([`6264533`](https://github.com/foryouself83/harness-tier/commit/62645339f21b63fad6fc45e516364d83331b3549))

- **flow-init**: Warn about a session below the top
  ([`d4c6bf1`](https://github.com/foryouself83/harness-tier/commit/d4c6bf11f52174fd0c4a719e0f3d99eb68525c49))

- **flow-uninstall**: Report what cleanup leaves
  ([`0f4affb`](https://github.com/foryouself83/harness-tier/commit/0f4affb73fc67f5eb17629bf1b9e170ffffbc7a1))

- **flow-uninstall**: Unify hook file cleanup
  ([`f83ded2`](https://github.com/foryouself83/harness-tier/commit/f83ded2ed043c68761d5ce2037c0e1e6c0f5b4f1))

- **gate**: Judge merges, commits where they land
  ([`0a889b2`](https://github.com/foryouself83/harness-tier/commit/0a889b220da64f4155145a0705c6bc8017acb488))

- **gate**: Keep the merge verdict linear in length
  ([`dcbf6ac`](https://github.com/foryouself83/harness-tier/commit/dcbf6acdfdeefa7183fbac46de3217af32d4a43e))

- **gate**: Read a substitution as one operand word
  ([`b8e1a78`](https://github.com/foryouself83/harness-tier/commit/b8e1a7898f40f313e28d9e4e8b805d240d4649fb))

- **gate**: Read empty values and bundles like git
  ([`865d879`](https://github.com/foryouself83/harness-tier/commit/865d879f9c0f95b167ddce1a004e25df0d5a6b1c))

- **gate**: Read here-strings as one operator
  ([`dbd151f`](https://github.com/foryouself83/harness-tier/commit/dbd151f58d5bcb68ecdf1112f2e7da75fa5a6cb4))

- **gate**: Read merge flags the way git does
  ([`aedb412`](https://github.com/foryouself83/harness-tier/commit/aedb4128c58438afbda7dea43c8b008488cd9ccb))

- **gate**: Read quote-split git subcommands
  ([`4ed5c0f`](https://github.com/foryouself83/harness-tier/commit/4ed5c0f6df351e34e81c0a3559a7631908b66e00))

- **gate**: Read quote-split merges as bash does
  ([`dcb7eb9`](https://github.com/foryouself83/harness-tier/commit/dcb7eb9898bf6547163e7254e6e71a71c5afbb4d))

- **gate**: Read quoting the way bash removes it
  ([`3001530`](https://github.com/foryouself83/harness-tier/commit/30015303fe29d1fb19e4d5506a37d2b3ecc43f80))

- **gate**: Read redirections and eval as bash does
  ([`0d35207`](https://github.com/foryouself83/harness-tier/commit/0d3520702de48920c492d110e22d71abf1b6daf9))

- **gate**: Show merge-check notices to the user
  ([`b7c8e0a`](https://github.com/foryouself83/harness-tier/commit/b7c8e0a9c0e8d209d3518ddaeea06e715ef644b7))

- **hooks**: Fire on every session and user wait
  ([`2db6e26`](https://github.com/foryouself83/harness-tier/commit/2db6e26edd757a3480426b9a662c0918bdb48430))

- **prose-review**: Keep paths with spaces whole
  ([`1dba314`](https://github.com/foryouself83/harness-tier/commit/1dba314d62f1b0fa5d70381b78dbb215ade9d62b))

- **release**: Repair release template failures
  ([`6988833`](https://github.com/foryouself83/harness-tier/commit/698883322236303c74102c54d4b9d38eeae49909))

- **rules**: Cut the injected session context
  ([`59ff907`](https://github.com/foryouself83/harness-tier/commit/59ff907d8f746a8ec63f7beb75b2c806bc642f8c))

- **skills**: Run each shell block on its own
  ([`c8f2032`](https://github.com/foryouself83/harness-tier/commit/c8f203224d4c37f487d5c605539319394376c9a2))

- **teams**: Keep branch webhook URLs out of git
  ([`73d4093`](https://github.com/foryouself83/harness-tier/commit/73d40931b363c7a8e526d900e013f85cfa39ca51))

### Documentation

- Move the developer CLAUDE.md under .claude/
  ([`7e182d1`](https://github.com/foryouself83/harness-tier/commit/7e182d1ca73dbf58d9d55ae78f806838a718c51a))

### Features

- **readme**: State that skills are measured
  ([`e8b4fb6`](https://github.com/foryouself83/harness-tier/commit/e8b4fb6d98db9e22333514be9ad2552b75b61e51))


## v0.4.3 (2026-10-01)

### Features

- **rules**: Commit message format moves to `rules/commit-discipline.md`, read by `/commit`,
  so `risk-tiers.md` and every session's injected context shrink. `/flow-init` copies
  `doc-style.md` into `.claude/rules/harness-tier/`, where Claude Code loads it, and the
  SessionStart hook drops its prose summary there; Codex keeps the hook summary.
  `/flow-uninstall` deletes the copied rules, never the host's own.

### Bug Fixes

- **hooks**: An unknown `--harness` value injects the Claude-form rule plus a block naming the
  bad arguments, and the marker hook voids the review and doc-sync evidence and exits 2. Bad
  arguments are cut to printable ASCII with `<` and `>` replaced, so they cannot break the
  injected JSON or the block they are quoted in.
- **hooks**: Session start is faster: the rule is escaped in the C locale and without
  subshell forks (Git Bash 962 → 118 ms, median of n=7; macOS bash 3 escapes
  through one awk call). Output is byte-identical.


## v0.4.2 (2026-09-29)

### Features

- **codex**: The plugin installs and runs on OpenAI Codex CLI. `/flow-init` registers the
  commit gate in `.codex/hooks.json` when flow-config `harnesses` names `codex`, injects the
  risk-tiers rule at Codex SessionStart, voids gate evidence on `apply_patch` edits, and
  renders CLAUDE.md and `.claude/rules` into a managed block of root `AGENTS.md`. Claude-only
  hosts keep byte-identical setup output.

### Bug Fixes

- **hooks**: Both hooks reject any argument other than `--harness claude|codex`, and the
  marker-invalidation notice names each voided gate once.


## v0.4.1 (2026-09-26)

### Features

- **release**: A staging promotion chooses its bump level (auto, continue, patch, minor,
  major) through a `Release-Level:` trailer; every release template shares one next-version
  block and a finalize guard that refuses a stable tag that exists or sits below the latest
  one.
- **release**: A stable release folds its rc sections into one deduplicated changelog
  section, published as the GitHub Release notes.

### Bug Fixes

- **license**: Add the third-party notice for ponytail (MIT).


## v0.4.0-rc.1 (2026-09-22)

### Bug Fixes

- **hooks**: Stay armed when the config read fails
  ([`89dd637`](https://github.com/foryouself83/harness-tier/commit/89dd637d92e8a01436786b6f474dc0799b5c0ee3))

- **shipped**: Defects that fail without a signal
  ([`36928c1`](https://github.com/foryouself83/harness-tier/commit/36928c1f8e5dff3715a710d578fa78bbb2aa32ed))

### Features

- **doc-style**: Make a comment the last resort
  ([`6a120dd`](https://github.com/foryouself83/harness-tier/commit/6a120dda53eb49403ef7053b9eb9a54f88ebeaf7))

- **docs**: Split USAGE into docs/usage/ topics
  ([`2671e2a`](https://github.com/foryouself83/harness-tier/commit/2671e2ae212abc3a4261643ed189fff988285911))

- **harness-authoring**: SRS readable by non-devs
  ([`5dee2c6`](https://github.com/foryouself83/harness-tier/commit/5dee2c6c607661a05320a137394f143d5fb47948))

- **skills**: Design deliverable skills to docx
  ([`c47ce96`](https://github.com/foryouself83/harness-tier/commit/c47ce9666a75d23b2fe8f07f2119d1a6808eb67d))


## v0.3.3-rc.1 (2026-09-12)

### Bug Fixes

- **commit**: Ban a CI-skip marker in the message
  ([`a7085f6`](https://github.com/foryouself83/harness-tier/commit/a7085f65477434fd405de55effb25df49bd766a2))

- **doc-style**: Carry the rule's own carve-outs
  ([`5176e02`](https://github.com/foryouself83/harness-tier/commit/5176e021094fcfbc09ddb2f4dcc0a17467c0ec35))

- **doc-style**: Keep superpowers docs out of scope
  ([`b7a1807`](https://github.com/foryouself83/harness-tier/commit/b7a18070116a81650f2a4619068a742675c19e8c))

- **docs**: Correct two overstated scopes
  ([`cfa0418`](https://github.com/foryouself83/harness-tier/commit/cfa0418a3eceba9cc3d92da135bc762cda135bf4))

- **gate**: Close invocation-classification gaps
  ([`602c11a`](https://github.com/foryouself83/harness-tier/commit/602c11aecb4f92f2ffd6b32cb6c8fdcad793ec0f))

- **gate**: Make the command scan linear
  ([`eec256e`](https://github.com/foryouself83/harness-tier/commit/eec256e7cb6a23419d4c0d9ae3367e076f6d6e3d))

- **gate**: Restate the cd-prefix difference
  ([`356f755`](https://github.com/foryouself83/harness-tier/commit/356f755b56c483f5bb0877bd128b695b4f439581))

- **hooks**: Give the injected rule a base path
  ([`eafd31b`](https://github.com/foryouself83/harness-tier/commit/eafd31b8d8413fedf02cb3be73785bbbdb432e43))

- **release-commit**: Say when to reach for it
  ([`4f1eb61`](https://github.com/foryouself83/harness-tier/commit/4f1eb6180d0f9e72e4f56cc5005cfcab432080cd))

- **rules**: Finish the pointer and SSOT sweep
  ([`9609e8f`](https://github.com/foryouself83/harness-tier/commit/9609e8fc46d9375b3197cd8c80f7708d8d1f1555))

- **rules**: Make pointers and claims resolve
  ([`f303f42`](https://github.com/foryouself83/harness-tier/commit/f303f4278fb672e485cb59b17adb8c64b30ba3fa))

- **scripts**: Keep i/o utf-8 on non-utf-8 hosts
  ([`1ca594d`](https://github.com/foryouself83/harness-tier/commit/1ca594d5eaafb9e821509e8e4c7e376c35d81f62))

- **tiers**: Mark promotions superpowers-OFF
  ([`22cfac3`](https://github.com/foryouself83/harness-tier/commit/22cfac3bf95d9f17cf8f9b8cb96b57cf85004e37))

### Documentation

- **claude-md**: Absorb what only memory held
  ([`a1f94ea`](https://github.com/foryouself83/harness-tier/commit/a1f94ea6a16788103bb861d92498e05bdab3db71))

- **claude-md**: Cut to rules and pointers
  ([`acd1fb3`](https://github.com/foryouself83/harness-tier/commit/acd1fb3a0154af81bb57cff83724eb2e1913455e))

- **rules**: Load the shipped rules here
  ([`bab3c17`](https://github.com/foryouself83/harness-tier/commit/bab3c17245eb79237e21fdd4d9fabc356645eba6))

- **scripts**: Drop filler words from comments
  ([`6df1764`](https://github.com/foryouself83/harness-tier/commit/6df17647916fa91f89c18f5c02d6b22d05aea29d))

### Features

- **ci**: Make wiki-verify and doc-style opt-in
  ([`200819b`](https://github.com/foryouself83/harness-tier/commit/200819b6214037e70cc7a8e25a7097210d2fd277))

- **doc-style**: Flag unmeasured magnitude claims
  ([`37f113a`](https://github.com/foryouself83/harness-tier/commit/37f113a3e747565eebd60b62bb725d0ee1c8d681))

- **doc-sync**: Run in a forked subagent
  ([`17b7545`](https://github.com/foryouself83/harness-tier/commit/17b7545536c5aed0aa0a11ca9047016bac813175))

- **srs**: Make SRS/SDS the requirement-text SSOT
  ([`b454b41`](https://github.com/foryouself83/harness-tier/commit/b454b41aa4fb7bbd7f331b60bd4f02c650156550))


## v0.3.2-rc.1 (2026-09-08)

### Bug Fixes

- **authoring**: Setext headings survive CRLF
  ([`73ea98d`](https://github.com/foryouself83/harness-tier/commit/73ea98d7403dc151a59f20fc04b6c200c044e9be))

- **flow**: Keep promotion detail out of the mandate
  ([`3a66097`](https://github.com/foryouself83/harness-tier/commit/3a6609783972c972f28d5b0eb8f3cbb577b158e8))

### Documentation

- **claude-md**: Name promotion.md in rules/
  ([`013a3d4`](https://github.com/foryouself83/harness-tier/commit/013a3d47cdb7823a85bf8a42b4a5cee0f40cce2f))

- **specs**: E2E CI safety net design and plan
  ([`6ab5222`](https://github.com/foryouself83/harness-tier/commit/6ab5222a89d116b15d9c4865176033f58c34dc17))

- **specs**: Promotion skill design and plan
  ([`e80a4f6`](https://github.com/foryouself83/harness-tier/commit/e80a4f6ffabcbf4e6b947f3ba60baed50d776713))

### Features

- **e2e**: Render a token-free Playwright workflow
  ([`e6c3d2d`](https://github.com/foryouself83/harness-tier/commit/e6c3d2df7c2232191724fd909ced2cfef1842daa))

- **flow**: Give promotion its own skill
  ([`fd179d9`](https://github.com/foryouself83/harness-tier/commit/fd179d98417361aeec4e3c48b7d775b95b1882f0))


## v0.3.1-rc.1 (2026-09-07)

### Bug Fixes

- **wiki**: Doc-sync survives an old host copy
  ([`d8b9bc9`](https://github.com/foryouself83/harness-tier/commit/d8b9bc9e8e42051ab5945e41fdf59d52e8bbb9a6))

### Features

- **wiki**: A design document maps to its code
  ([`9ab5142`](https://github.com/foryouself83/harness-tier/commit/9ab51422aa72daa3e906a0d5837077c709b4156d))


## v0.3.0-rc.2 (2026-09-06)

### Features

- **gate**: No command escapes the gate unjudged
  ([`1b5d89e`](https://github.com/foryouself83/harness-tier/commit/1b5d89e0ca76cb96096214d7d9f085c8594dfb61))


## v0.3.0-rc.1 (2026-09-05)

### Bug Fixes

- **gate**: Find a command where a shell starts one
  ([`bdbf46b`](https://github.com/foryouself83/harness-tier/commit/bdbf46b4fcd8da9b4ab2bb9bbcdd6ca1f14402d0))

- **gate**: Gate by default, exempt only readers
  ([`946f62b`](https://github.com/foryouself83/harness-tier/commit/946f62b77d5715572d00836a5e5b51dbdcfc1536))

- **gate**: Read the program at every command
  ([`2f2fd16`](https://github.com/foryouself83/harness-tier/commit/2f2fd16a1c3aa222b2e1bdb76960de90736f6f00))

- **init**: A half-copied install under-gates
  ([`da42dea`](https://github.com/foryouself83/harness-tier/commit/da42dea247419f57576d42f270f3def8e6483c79))

- **init**: Install a gate the host can read
  ([`72ec8c4`](https://github.com/foryouself83/harness-tier/commit/72ec8c4db30344d1d9776dec417521a2d6dba440))

- **init**: Read the matcher the way hooks do
  ([`c79b678`](https://github.com/foryouself83/harness-tier/commit/c79b6784528aa4223d188c373176b7634934fe07))

- **prose**: No shipped line runs past 300 chars
  ([`a14c0bd`](https://github.com/foryouself83/harness-tier/commit/a14c0bdc18c84e7fb1eb9ba129b2455d6c24c261))

### Features

- **gate**: An edit voids the review evidence
  ([`6cddf51`](https://github.com/foryouself83/harness-tier/commit/6cddf512548bd4be5391bcac7aa1dd54b1467489))

- **gate**: Prose discipline, mechanically checked
  ([`c6ca712`](https://github.com/foryouself83/harness-tier/commit/c6ca712e43e274dabf73476c7229a407ea4c0a5e))


## v0.2.3-rc.5 (2026-09-02)

### Bug Fixes

- **gate**: Read the commit an interpreter runs
  ([`0db7e5c`](https://github.com/foryouself83/harness-tier/commit/0db7e5ce1464295bbedbafb7a8ef93c61a89632e))


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
