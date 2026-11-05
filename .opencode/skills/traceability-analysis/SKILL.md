---
name: traceability-analysis
description: Analyze SDD requirement coverage, criterion verification links, changed specifications, dependencies and orphan references using explicit selected document records. Read-only; use for impact and coverage review, never for marking roadmap progress or replacing governance checkpoints.
---

# Traceability analysis

```bash
python3 scripts/traceability.py
```

Read selection and prerequisite paths from `knowledge-config.json` → `traceability`.
A real analysis requires constitution and capability registry. `not_initialized` means
bootstrap is needed; do not create a constitution, roadmap or traceability links to satisfy it.
For explicitly synthetic cases only, use `--input <selection.json> --fixture`; report fixture
mode and never present it as real project coverage.

The script reads only selected Markdown records with explicit `sdd-node`/`sdd-edge` comments.
It prints findings and evidence to stdout, never modifies SDD state. Coverage requires valid
explicit references and current source hashes. Inferred/disputed links never cover a requirement.
`VERIFIED_BY` denotes a linked validation record, not proof that a test passed. Missing pinned
specification hashes mean unknown impact, not unchanged artifacts.

If diagnostics disable coverage, report orphan references and errors first; do not claim an
empty gap list proves completeness. The constitution's `## Roadmap` remains the sole progress
authority. This capability supports review; it does not replace the SDD governor/checkpoints.

See [the selective ingest contract](../../../docs/graphrag.md) for record syntax and examples.
