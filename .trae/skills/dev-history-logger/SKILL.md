---
name: "dev-history-logger"
description: "Records detailed development history to '开发历史记录.md' in reverse chronological order. Invoke when user says 'RC'."
---

# Development History Logger

This skill automatically logs the current development progress into `开发历史记录.md`.

## Instructions

1.  **Check for '开发历史记录.md'**:
    *   If it exists, read its content.
    *   If it does not exist, create it with the header `# 开发历史记录`.

2.  **Generate DETAILED Summary**:
    *   Analyze the recent conversation history, file changes, and tool outputs comprehensively.
    *   **Do not omit important details.** Include:
        *   **Context**: What triggered the current task?
        *   **Changes**: Specific files modified, functions added/changed, bugs fixed.
        *   **Decisions**: Why certain approaches were chosen (rationale).
        *   **Status**: Current state of the project (working, broken, pending verification).
        *   **Next Steps**: What needs to be done next.
    *   Format the summary as a new section with a timestamp (e.g., `## 2026-02-21 10:00:00`).

3.  **Insert at TOP (Reverse Chronological Order)**:
    *   **CRITICAL**: The new summary must be inserted **IMMEDIATELY AFTER** the main title `# 开发历史记录`.
    *   Do NOT append to the end of the file.
    *   The goal is to have the **newest entry at the top** of the document, pushing older entries down.

4.  **Confirmation**:
    *   Inform the user that the history has been updated with the latest details at the top.
