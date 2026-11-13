# Independent corrected CLI29 review

**Verdict: PASS — Standards and Spec/runtime, bounded to the frozen completion change.** No blocking findings. This is an independent Codex review; unavailable external model families were not replaced by a claim of model diversity. No publication or production action was performed.

## Identity and review boundary

- Head: `a255bf04e890842ceb629792428eef0b63ec24e7`
- Tree: `55a4078b63b33f40b048ac71ac1d67757c078fdc`
- Base: `eadee13e05ed5c1cbd6116043b8868a2f9ec9666`
- Previous reviewed head: `29a6d3d9b3b9c13b4b30fbf3c8d0bf8bfebf4d73`

I read all nine changed files against the base, the complete hosted-fix handover and diff, the fresh comment review, the old independent review and next-step note, repository design/domain guidance, and the completion callers and current parser grammar. The previous-head delta is exactly `DESIGN.md` and `tests/test_completion.py`; product modules, workflows, build scripts and package metadata are unchanged. All eight wheel-member names and contents match the previously reviewed wheel. The current artifacts were nevertheless rebuilt and exercised independently.

## Standards: PASS

The parser extraction keeps command definitions in one place. Completion consumes that parser rather than maintaining a second command inventory. The implementation is small, dependency-free, and documents the current scalar/flag grammar boundary. The workflow delta installs Zsh for real tests and does not expand publication conditions or permissions. The two-file correction changes the insecure-directory fixture and its explanation. It does not weaken product validation or change release behavior. `git diff --check` passes; the detached source was clean before cleanup.

The fresh comment report is supporting context, not an independent runtime result. `#compdef uptible` is functional Zsh metadata, not removable explanatory prose.

## Spec/runtime: PASS

The correction uses `compinit -i -D`: auditing remains active and insecure paths are ignored. My separate real-Zsh probe verifies that `compaudit` identifies a temporary world-writable directory, excludes it after initialization, and still registers and executes an adjacent trusted completion function. A positive control with `compinit -u -D` registers and executes the unsafe function. Replacing the corrected fixture policy with `-u -D` yields 12 assertion failures; restoring old `-D` yields 12 noninteractive initialization failures. These controls exercise the behavior that could otherwise make a green test misleading.

Completion queries run before normal dispatch. Inspection and installed-artifact probes cover root and nested commands, aliases, flags, pending values, `--`, fixed choices, Bash byte cursors, Unicode before a suffix, open quoting, literal colon/equals and shell metacharacters. Oversized and malformed private-query inputs fail safely. Traps for dispatch, sockets, keyring, credential storage, browser and request calls stay untouched during completion; each trap is separately proven active. Candidate output is limited to parser-owned safe text, with no evaluation of a user's values. Shell wrappers invoke `command uptible`, bypassing shell functions.

## Fresh artifact evidence

| Lane | Full artifact gate | Installed completion | Actual interactive Tab | Additional boundary checks |
|---|---|---|---|---|
| macOS 26.6.2 arm64, Python 3.14.10, Bash 3.2.57, Zsh 5.9 | 87 tests; exit 0 | 7 restored wheel tests; 7 final-sdist tests; pip check passes | 16 ordinary cases plus 6 function-shadow/literal cases; stderr empty | 18 guarded results; 3 real audit-policy results; old/unsafe policies each produce 12 failures |
| Ubuntu 26.04.1 arm64, Python 3.14.4, Bash 5.3.9, Zsh 5.9 | 87 tests; exit 0 | 7 restored wheel tests plus 7 supplemental wheel tests and 7 final-sdist tests; pip check passes | 16 bounded-response ordinary cases plus 6 function-shadow/literal cases; stderr empty | 18 guarded results; 3 real audit-policy results |
| macOS Python 3.11.13 | Not a repeated full gate | Same current wheel: 7 completion tests; pip check passes | Covered by the Python 3.14 lane | Minimum supported Python smoke lane |

Each full gate independently builds twice, verifies exact committed module contents and dependencies, runs the installed suite with real Bash/Zsh, checks source restoration, and rejects all four deliberate faults: tampered dependency hash, extra wheel member, omitted completion command (4 failures), broken generated Bash (13 failures). The two build outputs agree within each run.

Current independent macOS and Linux wheel SHA-256: `4aa16167e1115e18d0fe480e0e0042f6166f98a57557fe1921f9111a8b9d18a6`.

Current sdist SHA-256 on both lanes: `2811dd175b6991647783bed1abfe92f426f36c142ea09451f5adee578ed3d4a4`.

The author's Linux wheel has a different hash (`862b62a6935b13dcb204e1f6c3f2876264b95df5fcde2fbaddaee511ab9ede52`). Direct comparison finds identical member bytes and four different ZIP external modes: author's `100666` versus this run's `100644`. This explains the observed difference; the result is not a promise of universal cross-host archive identity.

## Investigation and limits

The first supplemental Linux PTY attempt used the inherited fixed-delay driver. A Zsh literal-equals case failed with no capture response received before the driver’s short deadline. The failed stderr is retained. The independent replacement waits up to ten seconds for the actual editor-buffer response, rather than accepting another fixed-delay rerun. The replacement passes all 16 cases with actual captured buffer text and empty stderr. The six function-shadow cases also pass. The original failure does not establish why the shell response was late; no product change was needed to obtain direct buffer evidence. This is a test observation, not a performance measurement.

Both full gates emit the same two existing upgrade-test `ResourceWarning`s. On macOS the two named processes were directly observed absent after the gate. The Linux gate container terminated and was removed; I do not claim an individual in-container PID observation after removal.

The actual old GitHub-hosted head failed across Python 3.11–3.14, but the offending hosted `fpath` is unknown. A controlled insecure directory reproduces the original failure mechanism; this Ubuntu arm64 container is not an exact clone of the hosted runner. The corrected hosted matrix has not yet been observed green by this review. GitHub-hosted amd64, Homebrew installation/audit, and the wider application launch decision remain outside these fresh lanes. No credentials, provider operations, purchase, tag, release, package publication or forge mutation were used.

## Method and ownership

I applied poteto-mode's Standards/Spec review and Investigation playbook. `prove-it-works` led to rebuilding installed artifacts; `test-behavior-not-implementation` led to real PTYs, insecure-policy mutations and the independent shell-function-shadow control; `model-the-domain` kept the check tied to the actual parser grammar. `tap-the-sign` preserved the existing go-ahead while respecting the bounded review role. `land-the-plane` means completing evidence and cleanup here; the parent owns integration and publication decisions.

Raw local evidence remains outside the public packet. `PUBLIC/` contains sanitized portable copies, replay helpers and distributions, with a SHA-256 manifest. The ZIP contains only that packet. No private app data or machine/session-only evidence links are included.
