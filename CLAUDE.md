# CLAUDE.md

Conventions for this repository. These apply to every change, not just new files.

## Documentation-as-reasoning

Code in this repo carries its own justification. A reader — a reviewer, an interviewer, or you
in six months — should be able to understand not just what a piece of code does, but why it was
built this way and what it gives up.

This is enforced through docstrings at two levels.

### Function / logic level

Every function, method, or non-trivial block of logic gets a docstring covering four things,
in this order:

```python
def decompose_wall(wall: Wall, max_length_mm: int = 3700) -> list[Panel]:
    """Split a wall into transport-sized panels.

    Purpose:
        Divide a single wall segment into panels that fit the 3700mm transport
        constraint, preserving opening positions across the split.

    Why this implementation:
        Splits at even intervals rather than greedily filling max length, so
        panel widths stay uniform and the factory sees predictable jig setups.
        Openings are assigned to whichever panel contains their midpoint.

    Trade-offs:
        Uniform widths cost panel count — a greedy fill would use fewer panels
        for the same wall. Chosen because factory setup time dominates material
        cost at this scale. Revisit if panel count becomes the bottleneck.

    Edge cases:
        - Wall shorter than max_length: returns a single panel. Covered by
          test_single_panel_short_wall.
        - Opening spanning a split point: midpoint rule assigns it to one panel;
          the other panel gets no record of it. NOT fully handled — see
          ADR-00X. Guarded by a validation error, not silently accepted.
        - Zero-length wall: rejected upstream by the schema contract.
    """
```

Rules for the four sections:

1. **Purpose** — what it does, in the domain's language, not the code's.
2. **Why this implementation** — the reasoning that produced *this* approach. If an obvious
   alternative exists, name it and say why it lost.
3. **Trade-offs** — what this choice costs. Every real decision costs something. "No trade-off"
   is almost always a sign the trade-off has not been found yet; if you genuinely believe there
   is none, say so explicitly and briefly justify it.
4. **Edge cases** — enumerate them, and for each state whether it is handled, and how you know.
   Point at the test, the constraint, or the contract that proves it. **An edge case you have
   identified but not handled must be stated as unhandled**, not omitted. Silent omission is
   worse than a documented gap.

### Architecture / module level

Every module, package, or service that represents an architectural decision gets a module-level
docstring at the very top of the file, with the same four sections scoped to the architecture:

```python
"""Persistence layer for pipeline runs.

Purpose:
    Project the pipeline's file artifacts into a queryable relational read-model,
    so the API can answer questions the filesystem cannot (filter by status,
    resolve a panel within a job, trace a sequence DAG).

Why this architecture:
    Derived read-model, not source of truth — artifact bytes on disk remain
    authoritative, and this schema is regenerable from them. Validation runs
    before any ORM object is constructed, so a bad artifact cannot produce a
    half-written job row.

Trade-offs:
    Duplicates data that already exists in the artifacts, and must be kept in
    sync when the contract changes. Accepted because query-time joins across
    fifteen entity types are not feasible against flat files.

Edge cases:
    - Partial projection on failure: prevented by the single-transaction
      boundary; test_validation_gate proves the tables stay empty.
    - Natural-id collision across retries: ids repeat by design, so uniqueness
      is scoped per job rather than globally.
    - Concurrent projection of the same job: NOT handled. No advisory lock
      exists yet. See ADR-00X.
"""
```

### Where this does not apply

Do not pad trivial code. A one-line property, a `__repr__`, or a pure getter does not need four
sections — a single summary line is correct. The four-section form is for code where a decision
was made. If you find yourself writing "Trade-offs: none" repeatedly, the docstring is being
applied where it does not belong.

### Relationship to ADRs

Docstrings capture local reasoning; ADRs in `docs/decisions.md` capture decisions that span
files or that future work must not silently reverse. When a docstring's "why" is really a
project-level decision, write the ADR and have the docstring point at it rather than restating
it.

## Sources

When a decision rests on external documentation, cite the primary source by URL, and verify the
claim actually appears there before citing it. Community best-practice repositories and blog
posts may inform exploration but do not constitute justification on their own. If a change has
no primary-source basis, either leave it undone or record it as a proposal — do not implement it
and dress it in a citation it does not have.

## Reporting

When reporting completed work, distinguish what was verified from what was assumed. Prefer
evidence over assertion: paste the query output, quote the log line, cite the test name. A green
check is not evidence that the right thing ran.

Conventions for this repository. These apply to code you write or modify. Existing code is not
retroactively in scope — but if you are already editing a function, bring its docstring up to
this standard as part of the change.

## Sources and research

When a decision rests on external information, the source's authority matters more than its
popularity. Prefer primary sources, in this order:

**Tier 1 — primary, authoritative. Use these as justification.**
- Official documentation of the library, framework, or standard in question
  (e.g. docs.sqlalchemy.org, alembic.sqlalchemy.org, fastapi.tiangolo.com, kubernetes.io)
- Specifications and standards bodies (RFCs, W3C, ISO, buildingSMART for IFC)
- Peer-reviewed papers and preprints, cited with identifier (arXiv ID, DOI) and authors
- Source code and changelogs of the dependency itself, when the docs are silent

**Tier 2 — informative, not authoritative. May guide exploration; may not stand alone.**
- Widely adopted community best-practice repositories
- Engineering blogs from the maintainers or from organizations running the thing at scale
- Conference talks

**Tier 3 — do not cite.**
- Stack Overflow answers, tutorial sites, aggregator articles, AI-generated summaries

Rules:

1. **Verify before citing.** Fetch the page and confirm the claim actually appears there. Do not
   cite from memory, and do not assume a Tier 2 source has correctly summarized a Tier 1 one —
   they frequently diverge. Where they conflict, the primary source wins and the divergence is
   worth noting.
2. **A Tier 2 source may point you at a decision, but the citation must be Tier 1.** If a
   popular repository recommends something, find where the official documentation says it. If
   the official documentation does not say it, the recommendation is an opinion — treat it as
   one.
3. **Cite by URL, and cite what you actually used.** For papers, include the identifier and
   authors so the claim can be traced.
4. **No basis, no implementation.** If a change has no Tier 1 support, either leave it undone or
   record it in the report as a proposal. Do not implement it and dress it in a citation that
   does not support it.
5. **Say when you could not find one.** "I could not find official documentation for this" is a
   valid and useful report. Silence is not.
6. **Documentation changes.** Pages get revised between versions. If a page contradicts an
   instruction you were given, follow the page and flag the discrepancy — the instruction may be
   stale.
