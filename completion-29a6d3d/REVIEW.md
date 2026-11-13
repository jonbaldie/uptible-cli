# Independent CLI completion review

**Verdict: APPROVE this bounded completion unit.** No blocking Standards, Spec, or runtime defect was found. This is an independent review of the current artifact, not approval of the full application or CLI launch. The reviewer used inherited Codex because configured external model families were unavailable. No model-diversity claim is made. No nested reviewers were used.

## Exact source and artifact

- Head: `29a6d3d9b3b9c13b4b30fbf3c8d0bf8bfebf4d73`
- Tree: `03f5efd033440aae7290bb82af49f643f312688e`
- Base: `eadee13e05ed5c1cbd6116043b8868a2f9ec9666`
- Wheel: `uptible_cli-0.1.0-py3-none-any.whl`, SHA-256 `1d61d0aa9c5e225514d92ad1edb884bf52b68337ed25398be35acd29d91f8b02`
- Source distribution: `uptible_cli-0.1.0.tar.gz`, SHA-256 `6134cae6fe8ae7b67f49e9e93a39b51ef343f90c1ddaf5cb2ee044722a56ff31`
- Installed main module: `2ef60227fa393831957f316d1949df1b2cc5040f7b4e96263af7153d9875eecc`
- Installed completion module: `b753379fac6650ef85214a166aaa39461fea82c0b9427c91cf83c282b9704c12`

Both independently built distributions match byte for byte on this host and interpreter. The fresh installed modules match this source. The detached source was clean before building and after all checks. The manifest records every selected dependency hash. Input hashes are:

| Input | SHA-256 |
| --- | --- |
| verification-requirements.txt | `587359cbd9407e2c90acfb53b0f6a94e0e08cb7b9e758edd8d64edb4f16262f3` |
| runtime-requirements.txt | `72e1771b2ac15527fff57059546f948331644ab1f95627b3258f9f5abbb8886b` |
| homebrew-resources.json | `a2b4eff722a1e0f9f6f7b85957ac70cfe195216cbb641aec748a8a2c1b056867` |

The author's earlier head was `2bfd0df`. Its wheel hash was `7b52c160000b7f6d0d7c5901e3e6374f3849e1fd0fd3bb7f2207ee67f623d471`; its source distribution hash was `7d34ea39b24b2879b085414a45525b87d12c4c357ef957d99caef5dbf9694aaf`. Those hashes are not current-head evidence. The current wheel has the same member list. Only completion.py and its RECORD entry have changed content. The redundant module docstring was removed, and the commit-derived archive timestamps changed. These differences explain the new distribution hashes.

## Standards and brief

The reviewer read the consolidated brief, author handover, separate comment correction and comment review, evidence readme, workspace and repository instructions, CLI design, domain guidance, and all nine changed files. Poteto-mode's investigation playbook, code-review, how, model-the-domain, prove-it-works, tap-the-sign, and writing guidance informed this review. Land-the-plane was read; this review ends before integration, which the parent owns.

The parser extraction preserves existing command definitions and normal dispatch and error handling. Completion reads the same parser used for execution. The current grammar contains zero-value flags, single-value arguments, fixed choices, positional values, and nested commands. The traversal covers these shapes. The alias control also exercises argparse aliases although the current product parser has none.

Generated adapters pass literal input through quoted arguments. Candidates come only from parser names and fixed choices, with a restricted output character set. Free-form values receive no suggestions. Private queries validate bounded envelopes and return before command dispatch. Existing normal-command behavior is covered by the installed synthetic suite. Documentation describes supported shells, setup, root-option placement, refresh, and limits. Workflow changes install Zsh before the existing artifact gate. No release permissions or publication rules changed.

## Executed checks

Commands below use paths relative to this review directory. They all exited 0 unless stated otherwise. Build dependencies and runtime dependencies were installed with the repository's hash-pinned requirement files. Installation used `--no-deps` for the reviewed wheel, followed by `pip check`.

| Command or check | Result |
| --- | --- |
| From source: `python3.14 scripts/verify-artifact.py ../artifact` | Exit 0. Two separate builds and runtime resolutions matched. All 87 installed tests passed in 188.302 seconds. |
| Gate: omit notifications completion | Expected rejection: 7-test suite failed with 4 failures. |
| Gate: break emitted shell syntax | Expected rejection: 7-test suite failed with 13 failures, including a Bash syntax error near `}`. |
| Gate: alter a dependency download | Expected rejection: pip reported packages do not match required hashes. |
| Gate: add unexpected wheel member | Expected rejection: package hygiene reported `unexpected-private-fixture.txt`. |
| Gate: restore completion module | Exact original text comparison passed, cached bytecode removed, all 7 completion tests passed in 7.628 seconds. The gate's temporary installations were then removed. |
| Python 3.11.14: fresh environment, hashed dependencies, reviewed wheel, `python -m unittest discover -s source/tests -p test_completion.py -v` | All 7 tests passed in 7.474 seconds. |
| Python 3.14.10: same fresh-install check | All 7 tests passed in 8.807 seconds. |
| `py314/bin/python ../verify-interactive.py py314/bin/uptible` | 16 actual PTY cases passed across Bash and Zsh. No marker was created. |
| `py314/bin/python verify-extra-pty.py py314/bin/uptible` | Initial exit 1: 23 of 24 exact-buffer expectations passed. The remaining observation is explained below. |
| `py314/bin/python verify-extra-pty.py py314/bin/uptible --cursor-control` | Exit 0. Native Zsh `compadd -- status` produced the same spacing as the reviewed adapter. |
| `py314/bin/python verify-extra-pty.py py314/bin/uptible --cursor-only` | Exit 0. Both Bash and Zsh completed at a cursor before an existing suffix. |
| `py314/bin/python verify-guarded.py` | Exit 0. Generation and bounded queries avoided dispatch, sockets, keyring, Store, requests, and browser. Six direct positive controls each triggered its guard. |

The actual terminal checks used macOS arm64, Bash 3.2.57 and Zsh 5.9. They pressed Tab in interactive shells and checked Bash's redraw or Zsh's editor buffer. Inputs were cleared before Enter, and child shells were killed and reaped. Original cases cover commands, nested commands, Boolean options, event options, numeric equals choices, punctuation, and literal command-substitution text. Independent cases add Unicode and quoted spaces, escaped spaces, equals values, long-option abbreviation, positional shell choices after `--`, backtick text, cursor placement before a suffix, unfinished quotes, pending free-form values, and command termination. No marker was created.

The independent guarded check also exercises a Unicode byte cursor before a suffix, too many words, oversized Unicode text, extra Bash-query arguments, negative offsets, and offsets beyond the line. Guarded queries emit only expected fixed candidates or empty output. Guard positive controls prove the dispatch, socket, credential, browser, and request traps are active.

## Retained observations

The first independent cursor-middle Zsh expectation required one space: `uptible auth status --help`. Zsh actually produced two: `uptible auth status  --help`. A minimal native completion function containing only `compadd -- status` produced the same buffer. The focused check then passed with Zsh's native spacing expectation. This is normal shell delimiter insertion, and it does not change parsed arguments. The initial failed result, native control, and focused recheck are retained rather than replaced.

The full installed suite emitted two subprocess ResourceWarnings in existing credential tests. Both named PIDs were absent when inspected after the gate. The suite and gate exited 0. No persistent child process was observed. The warnings are retained in the log and are not hidden as completion failures.

## Limits and ownership

Approval covers parser-derived local completion and its packaging checks at the exact head above. It does not establish live account behavior, operating-system keyring support, Windows support, cross-host reproducibility, hosted CI execution, Homebrew installation, production deployment, or whole-product launch readiness. No production login, provider action, release, tag, publication, deployment, forge write, or issue closure occurred.

The public-safe bundle contains sanitized text evidence, the two distributions, hashes, and replay helpers. Local checkout, home, audit, and temporary paths are replaced. It contains public CLI details and synthetic inputs only. The parent owns any attachment upload and must verify saved PR evidence accessibility.

All review processes are finished, and owned PTY children were reaped. The detached source, two isolated installed environments, raw local logs, and portable evidence remain under independent/ for parent replay. The parent owns their removal after integration and evidence publication. The original source and author's installed environment were left unchanged.
