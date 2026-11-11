# Domain Docs

This repo uses a single-context layout: `CONTEXT.md` and `docs/adr/` at the repo root.

## Before exploring

Read the root `CONTEXT.md` and ADRs in `docs/adr/` that touch the area you are about to work in.

Read `DESIGN.md` for the recorded client design decisions.

If these files do not exist, proceed silently. The `/domain-modeling` skill creates them lazily when terms or decisions get resolved.

## Use the glossary's vocabulary

When naming a domain concept in an issue, refactor proposal, hypothesis, or test, use the term defined in `CONTEXT.md`.

If a concept is missing, reconsider whether it belongs to the project or note the gap for `/domain-modeling`.

## Flag ADR conflicts

If a proposal contradicts an existing ADR, identify the ADR and explain why the decision should be reopened.
