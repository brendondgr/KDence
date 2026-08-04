---
name: planner
description: Use this skill when asked to create, refine, or evaluate an implementation plan, roadmap, migration plan, or structured sequence of work before coding in KDence.
---

# Plan Creation — KDence

Produce explicit, hierarchical, validatable implementation plans.

The plan **format** — sections, level of detail, what a step must contain — is in
[planner.md](planner.md). This file is the project-specific contract every plan must honour.

## When to use

- The user asks to "create a plan", "plan this out", "make a roadmap", or "break this into
  steps".
- A change needs a staged approach before any code is written.
- A plan must be validated, committed, or handed off phase by phase.

## Where plans live

Under [`docs/plans/`](../../plans/), one file per plan, named for what it does
(`phase-9-historical-navigation.md`, `mobile-responsive-overhaul.md`). They are the durable
build record: a finished plan stays as the account of *why* something was built that way, while
[`docs/documentation.md`](../../documentation.md) carries what is *true now*.

[`activity-tracker-build-plan.md`](../../plans/activity-tracker-build-plan.md) is the
authoritative build order. New plans extend it rather than competing with it.

## What every KDence plan must do

### Carry the Review + Test rhythm

Every step ends with **two** passes, each with an explicit **Pass condition**:

1. **Review** — read what you built; confirm it does what the step intended.
2. **Test** — prove the behaviour.

A step is not done until both pass. State the Pass condition concretely ("the totals reconcile
with the raw store", "an evicted script re-injects") — never "it works".

### Respect the seam

Pure logic must stay separable from hardware-dependent code (DBus / KWin / Wayland idle /
MPRIS). A plan that puts logic behind a hardware call has designed something untestable. For
each step, say which side it lands on and where its test goes:

- pure logic → `src/kdence/<area>/<module>.py`, tested headlessly in `tests/<area>/`
- hardware seam → a separate module, at most a `@pytest.mark.live` smoke test

### Name real locations

Files, classes, functions, endpoints, config paths — the actual ones. Check they exist (or say
they are new). No code blocks in the plan; names and rationale only.

### Budget dependencies at zero

`dbus-fast` is the only runtime dependency. If a step needs a second one, that is a decision the
plan must surface explicitly with its justification — not a line item.

### Flag the privacy surface

If a step touches window titles, in-app detail, browser data, network binds, or anything written
to disk, say so and state the default. The default is always the **more private** option.

### Separate the human gates

KDence has real work that no agent can verify — anything needing a live KDE/Wayland session, a
stopwatch, or a full day of elapsed time. Plans must list these separately as **live gates**
rather than marking them done, and land them in [`docs/checklist.md`](../../checklist.md).

### End each phase with a commit

**Commit only — do not push** unless the user explicitly asks. Wording:

```
[Plan Name] (Current/Total) Complete: <what was done>
```

### Include the docs in the deliverables

Every plan's deliverables table names which of `structure.md`, `documentation.md`,
`workflow.md`, `checklist.md`, `honesty-review.md`, and `design-system.md` the change will make
stale, and updates them in the same commit. See the maintenance table in
[`docs/workflow.md`](../../workflow.md).

## Output shape

Clean Markdown: an introduction, gaps and unanswered questions, hierarchical steps with
locations and rationale, and a deliverables table. State an assumption for a simple gap and
proceed; mark a genuinely blocking gap as needing human input rather than guessing.
