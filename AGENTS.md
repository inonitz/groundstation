# AGENTS.md

## Autonomous Workflow Stages

### Phase 1: Context & Discovery

- Inspect workspace. Find relevant code blocks.
- Track down gaps. Do not guess.

### Phase 2: Recursive Planning

- Use scratchpad narrative to plan actions.
- Categorize steps strictly.

### Phase 3: Execution Loop

- Change code incrementally.
- Keep execution tight. Max 10 loops on stuck problem.

### Phase 4: Verification

- Verify changes against rules. Run checks.

## Stuck State Protocol

- Over 10 iterations on same issue? Stop. Ask human for context or output current data snapshot
