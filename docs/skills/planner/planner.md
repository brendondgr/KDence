# Plan Creation Reference

The output format for implementation plans. The project-specific contract — the Review/Test
rhythm, the pure/hardware seam, privacy flags, live gates — is in [SKILL.md](SKILL.md); this
file is the shape of the document.

Always output the plan as clean Markdown following the structure below.

---

## 1. Introduction

One or two paragraphs: what problem is being solved, and the overall approach.

> **Example**
> This plan adds a per-project breakdown under the existing in-app detail sub-dimension, so
> time in an editor can be attributed to the repository being worked in rather than only to the
> editor itself.
>
> The approach reuses the existing `DetailProvider` registry rather than adding a parallel
> path: a new pure policy resolves a workspace label from the caption the KWin script already
> reports, so no new sensing and no new dependency is involved.

---

## 2. Gaps and unanswered questions

List the gaps, edge cases, and unknowns *before* the steps, so nobody discovers them mid-build.

- **Simple gap** — state the most reasonable assumption and proceed.
- **Complex gap** — ask it explicitly and mark it: *"Human intervention is needed to answer
  this question."* Do not guess past a decision that would be expensive to reverse.

> **Example**
> - **Retention:** how long should raw spans be kept? *Assumption:* forever — the archive is
>   the point, and it is local-only.
> - **Attribution when two projects share a window title prefix:** *Human intervention is
>   needed to answer this question.*

---

## 3. Hierarchical step-by-step instructions

Sequential steps, each one a prerequisite for the next. Every step contains:

- **Locations** — the actual file names, classes, and functions that change. Mark new ones as
  new.
- **Rationale** — why this step, and why *here* in the order.
- **Side of the seam** — pure logic or hardware, and where its test lands.
- **No large code blocks.** Names and reasoning only; the plan is not the implementation.
- **Review + Test** — both passes, each with an explicit **Pass condition**.
- **Commit** — the phase's commit wording. **Commit only, do not push.**

> **Example**
>
> ### Step 2: Resolve a workspace label from the caption
>
> - **Locations:** `src/kdence/detail/workspace.py` (new, pure); registered in
>   `src/kdence/collector/providers.py`.
> - **Rationale:** the caption stream already exists, so this needs no new sensing — it is a
>   policy on data already flowing.
> - **Seam:** pure. Tests in `tests/detail/test_workspace.py`, headless.
> - **Review:** confirm the policy does no I/O and that a path never reaches the label.
> - **Test — Pass condition:** a caption carrying an absolute path yields the project name and
>   never the path; an unrecognised caption yields `None` rather than a guess.
> - **Commit:** `[Project Attribution] (2/4) Complete: pure workspace-label policy behind the
>   detail registry.`

---

## 4. Deliverables table

Close with a table of what will exist when the plan is done, and where.

Every plan's deliverables **must** include:

- **Tests** — in `tests/<area>/`, mirroring the code's area. Never in `utils/` or beside the
  source; this project keeps a single top-level test tree.
- **Documentation** — the canonical docs the change makes stale, updated in the same commit.

> **Example**
>
> | Deliverable | Description | Location |
> | --- | --- | --- |
> | Workspace policy | Pure caption → project label, no I/O | `src/kdence/detail/workspace.py` |
> | Provider registration | Priority slot in the detail registry | `src/kdence/collector/providers.py` |
> | Policy tests | Label resolution + path generalisation | `tests/detail/test_workspace.py` |
> | Structure map | New module recorded in the tree | `docs/structure.md` |
> | Honesty limit | What a project label does and does not prove | `docs/honesty-review.md` |
