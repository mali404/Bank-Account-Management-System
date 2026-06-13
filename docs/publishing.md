# Publishing Guide

This document is the playbook for taking the project from "works on my machine" to a publicly-visible portfolio piece.

## 1. GitHub repository

```bash
gh repo create mali404/agentic-bank --public --source=. --remote=origin --push
```

Add to the repo:
- **Description** (one line): "Hybrid multi-agent banking system with NIST-aligned security. LangGraph + FastAPI + Postgres + Ollama. PhD portfolio piece."
- **Topics**: `agentic-ai`, `langgraph`, `multi-agent-systems`, `rbac`, `nist-800-53`, `fintech`, `fastapi`, `postgres`, `ollama`, `opentelemetry`
- **Pinned README** badges (after CI runs once): build status, coverage, license, Python version.
- **Security policy** (`SECURITY.md`) — even a one-paragraph "report to email@…" entry helps.

## 2. Branch protection

In GitHub → Settings → Branches → main:
- Require pull request reviews before merging.
- Require status checks: `lint-and-test`, `bandit`, `codeql`, `trivy-image`.
- Require branches to be up to date.
- Don't allow force pushes.

## 3. Architecture diagram

The README ASCII works for casual scanning, but a polished SVG helps in a PhD application. Generate a versioned diagram via the Mermaid block already in `docs/architecture.md`. Export to `docs/img/architecture.svg` and reference it from the top of the README.

## 4. A short demo recording

Record `make demo` running while Jaeger UI is open in another window. 60–90 seconds. Embed as a GIF (asciinema → agg, or terminalizer) in the README under a "Demo" header. This single artifact converts more visitors than any written description.

## 5. Companion blog post

Useful framing for a PhD application — write a short post that explains:
1. The original 2023 course project (the "before" picture).
2. Why you'd rebuild it (research framing).
3. Three things you decided differently (LangGraph supervisor, hybrid LLM/deterministic split, OTel-first observability).
4. One genuine surprise — something the rebuild taught you that the original could not.

Publish on personal site or Medium. Cross-link from README.

## 6. PhD-application narrative

When linking this from your CV / SOP, frame it as the experimental platform for the research questions in `docs/research_notes.md`, not as a finished product. The questions are the substance; the code is evidence you can build the apparatus to investigate them.

## 7. Contributors and citations

Add a `CITATION.cff` so anyone who builds on this can cite cleanly:

```yaml
cff-version: 1.2.0
title: "Agentic Bank: A Hybrid Multi-Agent Banking System with NIST-Aligned Security"
authors:
  - family-names: Ali
    given-names: Munawar
date-released: 2026
license: MIT
url: "https://github.com/mali404/agentic-bank"
```

## 8. Maintenance cadence

- Monthly: rebuild the image (security patches roll forward), run `pip-audit`, glance at Dependabot.
- Quarterly: bump LangGraph / LangChain to the latest stable; re-run security tests.
- Annually: rotate the demo HMAC and JWT keys (script provided). Document the rotation event in a release note — this is the kind of detail reviewers notice.
