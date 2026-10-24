# Desktop assistant upgrade

Acceptance checklist. A feature is complete only after its implementation and relevant checks pass.

- [x] Always-visible composer, explicit microphone state, dedicated typing shortcut, accessible keyboard controls.
- [x] Action receipts distinguish observed success, execution without verification, failure and declined actions.
- [x] Saved workspaces: capture/edit named app layouts and restore with observable window checks.
- [x] Persistent reminders and timers, due notifications, snooze/cancel, restart recovery.
- [x] Project folder grants, bounded reading, reviewable edits/backups, approved build commands, cancellation.
- [x] Searchable conversation history and visible task stages/results.
- [x] Background jobs with status, logs, cancellation and recovery of interrupted jobs.
- [x] Longer configurable voice requests and file transcription instead of the fixed one-minute ceiling.
- [x] Opt-in meeting audio capture and locally transcribed meeting notes; explicit recording state.
- [x] Explicit custom MCP configuration and tool approval integration.
- [x] Native build/self-test, Python tests, browser checks and installed-app smoke checks.
- [x] Documentation states actual capabilities and any remaining constraints; no claim of universal correctness.

User data and local project grants stay in the per-user application data directory, outside the source repository. Existing Alt+Space toggle and Safe mode remain available.

Validation: Python regressions include real worker execution/cancellation, concurrent Windows locks, denied approvals, file backups/conflicts/revocation, reminder delivery/reload, mocked workspace frame verification and local stdio/HTTP MCP servers. The overlay passed 91 browser checks; the control centre passed 31, including layout widths 1020/720/390, escaping, draft retention and keyboard focus. Native build passed without warnings. Installed typing completed a real Codex request, background Codex completed a request and a read-only service call, a timer reached due through the running native scheduler, and the meeting file-transcription pipeline correctly processed synthetic speech across 75 seconds in three chunks.

Manual follow-up: actual meeting capture on the user's chosen audio devices and real third-party MCP accounts have not been exercised. Meeting notes are recorded transcription, not live speaker identification. Workspaces restore app window layouts rather than every application's internal document state. Folder grants, saved commands and external servers must be chosen explicitly in the control centre. Network/account/app permission limits remain real boundaries.
