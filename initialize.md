# Repository Initialization and Universal Agent Setup

This file is the initialization playbook for a new project repository. Its job is to guide an AI agent through project intake, documentation generation, skill selection, agent pointer creation, cleanup, and final verification.

The agent must not declare setup complete until the **Definition of Done** checklist near the end of this file has been verified.

**Important:** For Python projects, use `uv` as the package and environment manager unless the user explicitly states that the repository has no Python runtime. Record the final environment manager, install command, run command, test command, and lint/format commands in `docs/workflow.md` and the global project rules skill.

## Core Principle

The repository's durable instructions must live in `docs/`.

Agent-specific folders such as `.agents/`, `.claude/`, `.cursor/`, `.agent/`, and `.gemini/` are not the source of truth. They should contain only the minimum frontmatter and pointer text required by each tool, telling the agent which files under `docs/` to read.

For example, a generated repository should generally converge toward this pattern, adjusted for the user's actual project:

```text
ProjectRoot/
|-- docs/
|   |-- skills/
|   |   |-- global-project-rules/
|   |   |   `-- SKILL.md
|   |   |-- accessibility-mobile/
|   |   |   `-- SKILL.md
|   |   |-- ada-compliance/
|   |   |   `-- SKILL.md
|   |   |-- repository-structure/
|   |   |   |-- SKILL.md
|   |   |   |-- SETUP.md
|   |   |   `-- structures/
|   |   |-- website-architecture/
|   |   |   |-- SKILL.md
|   |   |   `-- SETUP.md
|   |   |-- planner/
|   |   |   |-- SKILL.md
|   |   |   `-- planner.md
|   |   `-- ui-frontend/
|   |       |-- SKILL.md
|   |       `-- ui/
|   |-- plans/
|   |-- checklist.md
|   |-- documentation.md
|   |-- structure.md
|   `-- workflow.md
|-- .agents/
|   `-- skills/
|       |-- global-project-rules/
|       |   `-- SKILL.md
|       `-- selected-skill-name/
|           `-- SKILL.md
|-- .claude/
|   `-- skills/
|       `-- selected-skill-name/
|           `-- SKILL.md
|-- .cursor/
|   `-- rules/
|       `-- selected-skill-name.mdc
|-- web/
|-- data/
|-- logs/
|-- utils/
|-- .env.example
|-- .gitignore
|-- pyproject.toml
|-- README.md
`-- uv.lock
```

This tree is illustrative, not mandatory. The final structure must match the user's project, but the `docs/` source-of-truth pattern is mandatory.

## Required Canonical Documentation

Create or update these files during initialization:

- `docs/documentation.md`: overall project purpose, tech stack, architecture notes, major decisions, and current status.
- `docs/structure.md`: canonical repository tree with the reason each top-level directory exists.
- `docs/workflow.md`: install, run, test, lint, format, build, environment, changelog, branch, commit, and handoff rules.
- `docs/checklist.md`: active project checklist. During initialization, this must include the setup Definition of Done and any known follow-up work.
- `docs/plans/`: directory for implementation plans and handoff plans.
- `docs/skills/`: canonical skill and rule definitions used by all agent tools.
- `docs/skills/global-project-rules/SKILL.md`: universal skill that every supported agent must read before working in the repository.

For website, dashboard, frontend, or API-backed web projects, also create or update:

- `docs/architecture.md`
- `docs/routes.md`
- `docs/component-map.md`
- `docs/data-flow.md`
- `docs/deployment.md`
- `docs/design-system.md`
- `docs/api-contract.md` when a backend or API contract exists

## Global Project Rules Skill

The global skill is mandatory. It defines repository-wide behavior expected from every AI agent.

Create `docs/skills/global-project-rules/SKILL.md` with:

- YAML frontmatter using a clear name and semantic description.
- The required files every agent must read before making changes.
- Environment manager requirements, especially `uv` for Python.
- Documentation maintenance rules, including when to update `docs/documentation.md`, `docs/structure.md`, `docs/workflow.md`, `docs/checklist.md`, and files in `docs/plans/`.
- Changelog or change-log policy if the project requires one.
- Testing and verification expectations.
- Cleanup expectations.
- Git workflow expectations if the user specifies them.
- A rule that setup is incomplete until the Definition of Done checklist has been verified.

Every agent-specific pointer must include a pointer to this global skill.

## Step 1: Project Intake

**AI Agent Instruction:** Ask enough questions to understand the project before selecting skills or creating files.

Start with:

> What is the primary goal and purpose of this repository? What are you building, who is it for, and what should exist when initialization is complete?

Then make sure the answers cover all required intake areas:

1. Project goal and intended users.
2. Primary deliverables, such as CLI, library, backend, website, dashboard, automation, data pipeline, research repo, or mixed application.
3. Runtime and framework choices, including Python, Node, web framework, database, or static-only tooling.
4. Expected top-level repository shape, such as single app, multi-app workspace, library, or tool collection.
5. Required directories and generated artifacts.
6. Data sources, integrations, auth, roles, and deployment target when relevant.
7. Supported agent tools or IDEs, such as Claude Code, OpenAI Codex, Cursor, Gemini CLI, or Antigravity.
8. Environment manager, install command, run command, test command, lint command, and build command.
9. Documentation policies, including changelog requirements, planning workflow, handoff expectations, and files that must always be read.
10. Cleanup expectations for starter directories and initialization helpers.

If the user gives incomplete answers, do not proceed silently. Ask follow-up questions. If the user is unsure, propose conservative defaults and ask for confirmation before Step 2.

Do not proceed to Step 2 until the intake answers are specific enough that another agent could scaffold the repository without guessing.

## Step 2: Skill Discovery and Selection

**AI Agent Instruction:**

1. Run `uv run read-yaml.py` if the file exists.
2. Recursively scan the repository for `SKILL.md` files and read their YAML frontmatter.
3. Cross-reference available skills with the user's goals and intake answers.
4. Propose a curated skill list and explain what each selected skill contributes.
5. Include `global-project-rules` as a required generated skill, even though it may not exist yet.
6. For any website, web app, dashboard, frontend, UI, or API-backed web interface, include `accessibility-mobile` and `ada-compliance` unless the user explicitly excludes them.

Wait for the user to confirm or modify the selected skill list before proceeding.

## Step 3: Setup Questionnaires

**AI Agent Instruction:** For each selected starter skill directory, read its `SETUP.md` file if present. Ask the user the relevant questions and record the answers for later use in `docs/`.

Examples:

- `repo-structure/SETUP.md` for repository layout and runtime decisions.
- `website-architecture/SETUP.md` for website, dashboard, frontend, route, data-flow, and API decisions.
- `ui-frontend/SETUP.md` for visual and UI system decisions.
- `plan/SETUP.md` for planning and handoff rules.
- `accessibility-mobile/SKILL.md` for mobile-responsive and touch-friendly web requirements.
- `ada-compliance/SKILL.md` for WCAG/ADA accessibility requirements.

If a selected skill has no `SETUP.md`, inspect its `SKILL.md` and supporting files, then ask only the missing questions needed to use it correctly.

### Required Website Architecture Branch

If the user's project goals mention a website, web app, dashboard, admin panel, frontend, UI, Flask, Django, FastAPI, Astro, SvelteKit, React, Next.js, Vite, static site, or API-backed web interface, or if either `repo-structure` or `ui-frontend` is selected for a web project, include and run the `website-architecture` setup phase before any UI generation.

For web-facing projects, include `accessibility-mobile` and `ada-compliance` in the selected skills. These two skills define the mobile-readiness and accessibility checks that must be reflected in `docs/workflow.md`, `docs/checklist.md`, and any UI implementation handoff.

For website projects:

- All site-specific code, assets, routes, and runtime files must live under the root `web/` directory unless the user explicitly chooses another layout.
- All repository documentation must live under `docs/`.
- The setup phase must produce a concise architecture planning artifact before Step 5.

The website planning artifact must define:

- application mode
- selected frontend framework and optional libraries
- user roles and auth boundaries
- route map
- data-flow map
- frontend/backend boundary
- design-system and anti-generic quality brief
- selected repository layout
- required documentation files
- build, run, and test commands

Wait for the user's response before proceeding.

## Step 4: Agent Environment Selection

**AI Agent Instruction:** Ask:

> Which IDEs or agentic programming tools should this repository support? Options covered by this initializer include Claude Code, OpenAI Codex, Antigravity, Gemini CLI, and Cursor.

Record the selected tools in `docs/workflow.md` and in `docs/skills/global-project-rules/SKILL.md`.

If the user selects no agent tools, still create the canonical `docs/skills/` files. Skip tool-specific pointer folders only if the user explicitly says they are not needed.

## Step 5: Generate Canonical Docs and Skill Sources

**AI Agent Instruction:** Generate or update the repository files using the approved skills, setup answers, website architecture artifact when applicable, and selected agent environments.

### Canonical Docs

Create the required `docs/` files first. These files are the source of truth and must be concrete enough that a future agent can continue without re-asking the same setup questions.

At minimum:

- `docs/documentation.md` must summarize the project, stack, architecture, and decisions.
- `docs/structure.md` must show the intended repository tree and explain each top-level path.
- `docs/workflow.md` must include setup, commands, environment rules, docs maintenance, and verification workflow.
- `docs/checklist.md` must include the setup checklist and any remaining project work.
- `docs/plans/` must exist.
- `docs/skills/` must contain canonical copies or generated versions of all selected skills.
- `docs/skills/global-project-rules/SKILL.md` must exist and be referenced by every agent-specific pointer.

### Canonical Skills

Move, copy, or synthesize selected skill definitions into `docs/skills/<skill-name>/`.

Preserve important supporting files from selected skills, such as:

- `SETUP.md`
- `planner.md`
- `structures/`
- `ui/`
- `references/`
- `scripts/`
- `assets/`

Do not leave the only copy of an active skill in a starter directory such as `repo-structure/`, `ui-frontend/`, `website-architecture/`, `plan/`, `accessibility-mobile/`, or `ada-compliance/`. Those starter directories are initialization inputs, not the final source of truth, unless the user explicitly chooses to keep them as canonical.

## Step 6: Generate Agent Pointer Files

**AI Agent Instruction:** For each selected agent tool, create only the pointer files needed by that tool. The pointer files must route the agent to `docs/skills/global-project-rules/SKILL.md` and the relevant canonical skill files under `docs/skills/`.

Do not duplicate long instructions in agent-specific folders. The same rule content should not be maintained separately in `.agents/`, `.claude/`, `.cursor/`, `.agent/`, or `.gemini/`.

### Directory Placement

| Tool | Project-Scoped Path | Global/User Path |
|---|---|---|
| Claude Code | `.claude/skills/<skill-name>/` | `~/.claude/skills/<skill-name>/` |
| OpenAI Codex | `.agents/skills/<skill-name>/` | `~/.agents/skills/<skill-name>/` |
| Antigravity | `.agent/skills/<skill-name>/` | `~/.gemini/antigravity/skills/<skill-name>/` |
| Gemini CLI | `.gemini/skills/<skill-name>/` | `~/.gemini/skills/<skill-name>/` |
| Cursor | `.cursor/rules/<rule-name>.mdc` | `~/.cursor/rules/` |

### Claude Code Pointer Format

Claude Code skills use `SKILL.md` with YAML frontmatter. In the agent-specific copy, keep the frontmatter valid and make the body a pointer.

```yaml
---
name: repository-structure
description: Use this skill when working with repository layout, setup, structure docs, or project organization.
---
```

```markdown
# Repository Structure

Read these files before acting:

1. `docs/skills/global-project-rules/SKILL.md`
2. `docs/skills/repository-structure/SKILL.md`
3. `docs/structure.md`
4. `docs/workflow.md`
```

### OpenAI Codex Pointer Format

Codex uses the same `SKILL.md` format and scans `.agents/skills`.

```yaml
---
name: skill-name
description: Explain exactly when this skill should trigger. The body points to canonical instructions in docs/skills.
---
```

Optional `agents/openai.yaml` metadata can be added only when the project needs richer UI metadata or behavior control.

### Antigravity Pointer Format

Antigravity uses the same `SKILL.md` format. `name` is optional but should be included for consistency.

```yaml
---
name: skill-name
description: Use this skill when the matching canonical docs/skills instructions apply.
---
```

### Gemini CLI Pointer Format

Gemini CLI uses `SKILL.md` with the same required fields. The `name` should match the directory name.

```yaml
---
name: skill-name
description: Description of when to read the canonical docs/skills version of this skill.
---
```

### Cursor Pointer Format

Cursor uses flat `.mdc` files in `.cursor/rules/`. Use valid frontmatter and then point to the canonical docs.

```yaml
---
description: Use this rule when working with repository setup, structure, or documentation.
globs: ["**/*"]
alwaysApply: false
---
```

```markdown
Read `docs/skills/global-project-rules/SKILL.md` first, then read the relevant canonical files under `docs/skills/`.
```

## Step 7: Cleanup

**AI Agent Instruction:** Cleanup is required, but it must happen only after canonical docs and pointer files are verified.

Delete or remove setup-only material when it is no longer the source of truth:

- Unselected starter skill directories.
- Selected starter skill directories after their useful files have been moved or copied into `docs/skills/`.
- Initialization helpers such as `read-yaml.py` when no longer needed.
- `initialize.md` only when the user agrees that initialization is complete and the file is no longer needed.
- Empty generated folders.
- Placeholder files that conflict with the completed project docs.

Do not delete:

- User-authored project files that are not part of the initializer.
- Active canonical files under `docs/`.
- Agent pointer files for selected tools.
- Required project runtime files such as `pyproject.toml`, `.python-version`, `uv.lock`, `.env.example`, or framework config files.

Record deleted and intentionally retained setup files in `docs/checklist.md` or `docs/documentation.md`.

## Step 8: Definition of Done

**AI Agent Instruction:** The repository is not initialized until every applicable item below is true. Verify each item explicitly before telling the user setup is complete.

### Intake Complete

- [ ] The project goal, runtime, deliverables, target users, supported tools, and validation workflow are known.
- [ ] All missing or ambiguous required answers were resolved through follow-up questions or confirmed defaults.
- [ ] Website architecture questions were answered if the project includes any web interface.

### Canonical Docs Complete

- [ ] `docs/` exists.
- [ ] `docs/documentation.md` exists and reflects the final project direction.
- [ ] `docs/structure.md` exists and matches the actual intended repository structure.
- [ ] `docs/workflow.md` exists and includes install, run, test, lint, build, environment, documentation, and handoff rules.
- [ ] `docs/checklist.md` exists and includes the setup checklist plus known follow-up tasks.
- [ ] `docs/plans/` exists.
- [ ] `docs/skills/` exists.
- [ ] `docs/skills/global-project-rules/SKILL.md` exists and names the required docs every agent must read.
- [ ] Every selected skill has a canonical folder under `docs/skills/<skill-name>/`.
- [ ] Supporting skill files such as `SETUP.md`, `planner.md`, `structures/`, `ui/`, `scripts/`, `references/`, or `assets/` were preserved when relevant.

### Agent Pointers Complete

- [ ] Every selected agent environment has the required project-scoped pointer files.
- [ ] Each pointer file has valid frontmatter for its tool.
- [ ] Each pointer file references `docs/skills/global-project-rules/SKILL.md`.
- [ ] Each pointer file references the relevant canonical skill under `docs/skills/`.
- [ ] No agent-specific folder contains the only copy of important project instructions.

### Project Structure Complete

- [ ] Required top-level directories for the selected project type exist.
- [ ] Website projects keep site code and assets under `web/` unless a different layout was explicitly chosen.
- [ ] Required runtime/config files exist or are documented as intentionally deferred.
- [ ] `.env.example` exists if environment variables are needed.
- [ ] `README.md` points readers to the canonical docs or summarizes the initialized project accurately.

### Cleanup Complete

- [ ] Unselected starter directories were deleted or documented as intentionally retained.
- [ ] Selected starter directories were deleted after migration to `docs/skills/`, unless intentionally retained.
- [ ] Initialization helper files were deleted or documented as intentionally retained.
- [ ] The final tree does not contain duplicate competing sources of truth.

### Verification Complete

- [ ] The agent listed the final repository tree or otherwise inspected it after cleanup.
- [ ] The agent opened and checked the generated canonical docs.
- [ ] The agent opened and checked representative pointer files.
- [ ] The agent verified that every pointer target exists.
- [ ] The agent ran applicable validation commands or documented why they were not run.
- [ ] Any remaining setup gaps are listed in `docs/checklist.md`.

If any checkbox fails, continue working or ask the user for the missing information. Do not claim completion.

## Step 9: Final User Report

Only after the Definition of Done is satisfied, tell the user setup is complete.

The final report must include:

- What was created or updated.
- Which agent environments were configured.
- Which starter files or directories were removed.
- Which files were intentionally retained and why.
- Which commands were run for verification.
- Any remaining follow-up tasks from `docs/checklist.md`.

If setup is partially complete, say that directly and list the blocking checklist items.
