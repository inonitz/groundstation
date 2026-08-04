# Project Documentation & Meta-Behavior Rules

When interacting with this workspace, you must adhere strictly to the following documentation and tracking protocols:

## Session & Conversation IDs
1. **Conversation Turn Tracking**: Every message must be uniquely identified.
   - User messages are denoted as `[USER-N]`.
   - Your responses must be denoted as `[SYSTEM-N]`.
   - Both start at 0 and ascend incrementally throughout the conversation.
2. **Session Tracking**: Each distinct conversation (run) represents a new Session (e.g., Session 0, Session 1, Session 2).

## Global Change IDs
1. **Unique Identification**: Every file modification, deletion, or creation you perform must be assigned a unique `[Change-N]` ID.
2. **Global Scope**: Change IDs are GLOBAL across all sessions. Do not reset them to 0 for a new session. Always check the existing `CHANGELOG.txt` to find the highest ID and increment from there.

## Documentation Artifacts
1. **scratchpad.txt**: You must document all of your planning, reasoning, and intended actions in `scratchpad.txt` BEFORE modifying project files. Use this file to log your thoughts per turn (e.g., under a `### Response [SYSTEM-N]` header).
2. **CHANGELOG.txt**: After finalizing changes, append them to `CHANGELOG.txt` grouped by the current Session.
   - Each entry must include its global `[Change-N]` ID.
   - You must specify which conversation turn (`[SYSTEM-N]`) prompted the change.
   - Format example: `- [Change-12] path/to/file.ext - Description of change (via [SYSTEM-4])`

**CRITICAL**: Review the changelog to ensure you are not reusing IDs and that your conversation IDs correctly reflect the current chat state.

## CHANGELOG Tracking Rule
- **Purpose**: Do NOT restrict `CHANGELOG.txt` to only code changes. You must actively use it (or `HISTORY.txt`) as a master document to record your thinking, planning, and intended work directions. This allows the user and future agent sessions to review past execution and verify alignment with previous plans.
- **Action**: After generating an implementation plan or making significant architectural decisions, summarize those thoughts and place them under the corresponding Session header in the changelog, including the relevant User/System IDs.

## Formatting Rule
- **Readability**: All documentation, especially the changelog, must be highly Human readable. Do NOT surpass 95 characters per line. Divide sentences into multi-line statements where required to enforce this width limit.

## Execution & Context Rule
- **Never Guess**: Never guess information. If you don't know, say that you don't know. You don't get rewarded for finishing something, you get rewarded for doing it in a correct & good way.
- **Context Gaps**: If you notice context gaps you can ask the user for more information or for further instructions, in order for you to close the aforementioned context gap.
