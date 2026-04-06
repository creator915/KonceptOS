# Multi-Tenant AI Delivery Platform

Build a production-style project around 10,000 lines of code.

## Product summary

This platform helps software teams plan, generate, review, and execute AI-assisted
delivery work. It combines:

- workspace management
- repository tracking
- architecture notes
- task planning
- prompt and seed management
- execution history
- approval workflows
- background job orchestration
- artifact storage
- observability dashboards

## Core capabilities

### Workspace and organization

- Multi-tenant organizations
- User invitations
- Role-based access control
- Workspace settings
- Audit trail for important actions

### Repository and architecture memory

- Register repositories and branches
- Store architecture notes and design decisions
- Track file ownership and module boundaries
- Attach contracts and seeds to project areas
- Show impact analysis for proposed changes

### Planning and execution

- Create epics, tasks, subtasks, and coding jobs
- Turn a natural-language request into a structured implementation plan
- Allow human approval before execution
- Run background coding jobs
- Store job logs, generated patches, and artifacts
- Retry or resume failed jobs

### Prompt, seed, and template system

- Manage reusable prompt templates
- Manage domain seeds and coding conventions
- Attach seeds to repositories or tasks
- Version prompt templates and seeds

### Review and verification

- Show impacted files and affected modules
- Track build, test, lint, and typecheck results
- Display review status for generated patches
- Preserve execution history and decision logs

## Technical expectations

- Use a realistic modular stack with frontend, backend, worker, and tests
- Include auth, data models, API routes, services, background jobs, UI pages, and test suites
- Include configuration, local dev tooling, and seed/example data
- Prefer clean module boundaries and shared contracts across layers
- Generate a repository that feels like an early internal product, not a toy demo

## Suggested shape

- Frontend: React + TypeScript
- Backend: FastAPI or similar Python web framework
- Data: PostgreSQL
- Worker queue: Redis-backed background worker
- Tests: frontend and backend tests

The repository should be large enough to approach 10,000 lines of code when generated.
