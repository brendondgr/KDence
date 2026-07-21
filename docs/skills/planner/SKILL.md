---
name: planner
description: Use this skill when the user asks to create, refine, or evaluate an implementation plan, roadmap, migration plan, or structured sequence of work before coding.
---

# Plan Creation

Use this skill to produce explicit, clear, and hierarchical implementation plans.

## Core Reference

Follow the planning format and quality rules in [planner.md](planner.md).

For the questionnaire that tailors plan output to this project, see [SETUP.md](SETUP.md).

## When To Use

- The user asks to "create a plan", "plan this out", "make a roadmap", or "break this into steps".
- The user needs a staged implementation approach before code changes.
- The user asks for a plan that can be validated, committed, or handed off phase by phase.

## Output Expectations

- Use clean Markdown with an introduction, gaps and unanswered questions, hierarchical steps, and a deliverables table.
- Include concrete locations such as files, classes, functions, scripts, or directories where work will happen.
- State assumptions for simple gaps and explicitly mark complex unanswered questions that need human input.
- Include validation expectations and commit wording for each phase when the plan is meant to guide implementation work.

## Project Conventions (KDence)

This project already has an active, test-driven build plan at
[docs/plans/activity-tracker-build-plan.md](../../plans/activity-tracker-build-plan.md).
New plans must:

- Preserve the build plan's **Review + Test + Pass condition** rhythm — a step is not
  done until both a read-back review and a behavioral test pass.
- Keep pure logic (time model) separable from hardware-dependent code (DBus / KWin /
  Wayland idle), so the logic can be unit-tested without a live session.
- End each phase with a **commit** (do not push) using the wording:
  `[Plan Name] (Current/Total) Complete: <what was done>`.
- Save new plans and handoff plans under `docs/plans/`.
