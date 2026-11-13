# Independent CLI artifact review

The goal is a reliable production launch of the Uptible app and CLI. This review covers the CLI packaging preparation at commit `61a24e1726b04e64734d457bb543c898dd9c331c`, based on main `0c068965e01a3c38bcb4388e169fb806eeeb4cf8`.

**Verdict. PASS+NOTES for the exact frozen packaging candidate.** I found no actionable correctness defect in the changed code. This verdict does not approve the whole launch, publication, production sign-in, or issue closure. The coordinator owns the current-head CI and clean hosted macOS Homebrew gate.

I read the complete 11-file patch, both packaging scripts and their previous implementation, package metadata, runtime input markers and hashes, formula resources, workflows, repository guidance, REPORT.md, ADVISORY-NOTES.md, and ADVISORY-DETAILS.md. I read the fresh COMMENT-REVIEW.md before this verdict. Its zero findings agree with my inspection. Source and all 80 tests are byte-identical to main.

## Independent execution

I cloned the candidate into an owned standalone checkout and mounted it read-only into a fresh Linux arm64 container. The container used image digest `python@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`, local image ID `sha256:c5ba0da6ef694b3d8d1bc8bc9a1beadd026f679fe2df2f31a366d70146a0b0ed`, and CPython 3.11.18. Git was installed only inside the disposable container.

The actual command `python scripts/verify-artifact.py /review-output` exited 0 against an initially empty output directory. The log is `linux311-verifier.log`. The results are retained in `linux311-output/`.

- Two separate Git archives, source directories, build environments, and runtime environments produced identical artifact and selected dependency hashes.
- Both runtime installs passed `pip check`. The first installed environment passed all 80 tests outside the source checkout in 86.824 seconds. That duration is a test result, not a performance claim.
- Version, help, installed import location, and the console entry point passed.
- The altered dependency failed with pip's hash mismatch. The unexpected wheel member failed the package allowlist.
- The committed source timestamp is 1794573203. The retained manifest identifies the exact commit and all three input files.

The resulting SHA-256 identities are:

| Artifact | SHA-256 |
| --- | --- |
| `uptible_cli-0.1.0-py3-none-any.whl` | `c0529f0dc62e40c50de804a5fa8bf05d83a378211a9d3c95246e72eae5408cee` |
| `uptible_cli-0.1.0.tar.gz` | `df8ef3507dd93764639790cbf66e1298fa1c5b712f669541d035a1428b310112` |
| Committed CLI module | `1b7b1b4ade0dec5d18d41d63e40c5102c5950d45eb2343cc1c7b14da6fb6b8a7` |
| `verification-requirements.txt` | `587359cbd9407e2c90acfb53b0f6a94e0e08cb7b9e758edd8d64edb4f16262f3` |
| `runtime-requirements.txt` | `72e1771b2ac15527fff57059546f948331644ab1f95627b3258f9f5abbb8886b` |
| `homebrew-resources.json` | `a2b4eff722a1e0f9f6f7b85957ac70cfe195216cbb641aec748a8a2c1b056867` |

I separately installed this wheel with the hashed runtime graph in another disposable Python 3.11 container. `authenticate-installed.py` authenticated the actual installed module bytes, prefix, metadata version, and entry point. An appended synthetic comment failed authentication. Restoring the exact bytes passed again. See `installed-authentication.log`.

I independently ran pip's actual metadata check on Python 3.10.22 using image digest `python@sha256:6ff506466f8b1e981719b468cc0023b8ef000b983cdec0eafe119d01f379e31d`. `python -m pip install --no-index --no-deps --dry-run` rejected the wheel with exit 1 and `3.10.22 not in '>=3.11'`. See `python310-rejection.log`.

## Independent controls and source identity

`python3 independent-checks.py` exited 0. The script compares actual Git bytes with wheel modules and source archive modules, tests, pyproject.toml, and README.md. It verifies normalized archive ownership, modes, timestamps, actual artifact digests, both build reports, both runtime reports, and input hashes in all three author matrices.

I authenticated the retained macOS 3.14.5, Linux 3.11.18, and Linux 3.14.10 manifests against the frozen source. Each matrix has identical within-host builds and resolutions, 80 passing installed tests, and both rejecting negative controls. Cross-host artifact equality happened in these observations. The supported claim remains two builds of the same commit on the same OS and interpreter with the same inputs.

The independent formula controls accepted the authentic manifest and rejected altered revision, version, source digest, resource-file identity, module digest, and modified sdist bytes. Unsafe URL interpolation, quotes, a newline, and plain HTTP were rejected. `ruby -c independent-uptible.rb` reported `Syntax OK`. These results are in `independent-controls.json` and `independent-checks.log`.

Synthetic tar controls rejected duplicate names, a symlink, absolute paths, parent traversal, and an unexpected file. A changed module payload survived normalization unchanged. Normalization therefore removes archive metadata rather than erasing a source difference. The actual source archive's modules match Git, and the wheel built through that archive matches Git as well. The wheel has exactly seven unique allowed members. The source archive validator allows a subset of its file allowlist and benign directories. It is a hygiene check on trusted build output, not a general-purpose parser for hostile archives.

## Portable inputs and security reasoning

The marker graph selects six runtime packages on macOS 3.14, eleven on Linux 3.14, and fourteen on Linux 3.11. The minimum-version additions include importlib-metadata, zipp, and backports.tarfile. Linux adds SecretStorage, jeepney, cryptography, cffi, and pycparser. Windows has a separate pywin32-ctypes marker without a Windows verification claim. This is a portable marked graph, not a single-host freeze.

`python3 check-pypi-inputs.py` independently fetched the version-specific primary PyPI metadata for all 21 exact pins. Every published wheel hash set matches the committed inputs, including all 83 cffi and 58 cryptography variants. All eight Homebrew source resource URLs and SHA-256 identities match the corresponding PyPI metadata. No version-specific advisories were reported at observation time. I also parsed the retained final PyPI and pip-audit snapshots by relevant fields and read the initial advisory reports. No undisclosed-vulnerability claim follows from these scans. See `independent-pypi-inputs.json` for exact primary URLs and the observation time.

Filelock 4.2.10 metadata requires Python 3.11. The approved prerelease minimum and public package ranges agree with the input graph and CI matrix. The existing client uses FileLock with explicit mode 0600 inside a directory checked for current-user ownership and no group or other permission bits on Unix. The critical section is unchanged. Shared-directory and other lock-class advisories do not establish thirteen reachable CLI exploits. Selecting the fixed upstream package avoids a custom locking rewrite. OS credential backend behavior is outside this proof.

The formula checks current Git revision, source archive digest, module identity, and committed resource manifest identity before rendering. The formula test authenticates the installed module and common dependency versions. I inspected the actual author Homebrew identity, install, test, strict-audit, 80-test suite, tampered installed-module rejection, and restored-module pass evidence. I did not repeat a shared Homebrew install or dependency upgrade.

## Limits and handoff

The clean hosted macOS Homebrew gate is a coordinator-owned requirement. This review does not substitute a second local installation for that gate. Homebrew itself, its Python, source resource build tools, and CPython's bootstrap tooling remain trusted external toolchain inputs. No reproducible Homebrew bottle or Linux Homebrew approval follows. Checksums authenticate bytes relative to the trusted manifest and Git commit. They are not publisher signatures.

This independent run covers Linux arm64 Python 3.11. The author evidence adds local macOS arm64 Python 3.14 and Linux arm64 Python 3.14. Other architectures, Windows, PyPy, OS keyring backends, production API compatibility, public installation and update, and production login remain unverified here. The configured non-Codex model families were unavailable. This fresh Codex reviewer supplies agent independence, not cross-family review diversity.

Issue 1's full command and API coverage and issue 24's original publication, public installation and update, and production login criteria remain open. Draft PR 25 must not land unchanged. The coordinator owns that disposition and PR 28's merge decision. The publication job remains tag-only and depends on build and Homebrew jobs. I created no tag, release, public tap, production login, provider action, customer message, or forge write.

Prove It Works changed the review from reading author claims to running the minimum interpreter and authenticating real bytes. Test Behavior, Not Implementation led to altered-input and installed-module rejection controls. Tap the Sign kept the work tied to launch readiness and the existing Go limits. I used CLI and Docker as the documented control-tool fallback. The parent runs the program playbook. Land the Plane applies here to verification and owned cleanup, with integration explicitly reserved to the coordinator.

The verifier removed its temporary build and runtime environments. All three owned disposable containers exited and were removed. I removed the owned standalone clone after the final runtime check. `cleanup.json` records a clean, unchanged source at the frozen head and zero owned containers. Other agents' runtimes and shared Homebrew state were untouched. Review scripts, small logs, and reproducible evidence remain in this directory. Raw diagnostics remain local. No private application source or credentials entered this review.
