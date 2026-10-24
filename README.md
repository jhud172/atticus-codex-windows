# Atticus for Windows — Codex edition

Independent source-available adaptation of [FindlayHi/atticus-windows](https://github.com/FindlayHi/atticus-windows), originally [SaarthurR/atticus-mac](https://github.com/SaarthurR/atticus-mac).

Atticus is a Windows tray assistant for typing, voice, desktop actions and project work. **Alt+Space** starts/stops voice; **Alt+Shift+Space** opens typing directly. The microphone button also toggles recording. Windows' usual Alt+Space menu is intercepted while Atticus is running. Esc cancels. Shortcuts and hold/toggle behaviour remain configurable in Settings.

Speech is transcribed locally with Whisper. Questions and approved actions use the **Codex CLI app-server**, signed in with your existing Codex account. Account limits apply.

## What you can use it for

Open the **Control centre** from the tray menu or the buttons in the assistant.

When a local setup proposal is available, **Review setup** shows its exact folders, saved command arrays and MCP definitions before any permissions are applied. Approval validates the proposal digest, validates every entry, backs up existing state and applies it together. The model cannot approve its own setup. Sign-ins remain separate from saving a connector definition.

| Feature | Example or setup |
| --- | --- |
| Typing and voice | Type a question immediately, or click the microphone. Its state is labelled explicitly. |
| Desktop help | “Open Notepad”, “Move Notepad to the right”, or ask about your screen. Supported actions depend on the app's exposed controls. |
| Workspaces | Capture current windows as “Study”, or define app entries; “Restore workspace Study” opens missing apps and checks their positions. |
| Reminders | “Remind me in 10 minutes to take a break”, or set a date/time in Reminders. Snooze/cancel in the control centre. |
| Project files | Add a specific folder in Projects. Ask to read files and propose an edit; review its diff before applying. Originals are backed up and stale previews are rejected. |
| Builds and tests | Save an executable/argument array for a granted project, then run it with approval. Follow output and cancel from Background tasks. |
| Research and longer tasks | Start a background request and continue using your PC. Results and task status persist locally. |
| Meeting notes | Explicitly start/stop recording system audio and microphone, or transcribe an audio file. Review the local transcript, then optionally send it to Codex for a summary. |
| Extensions | Configure a trusted MCP server in Extensions. Test tool discovery there; each model tool execution asks for approval. |
| History | Search previous questions/answers, repeat a request, and review observed/unverified action receipts. |

Voice requests default to five minutes and can be set to 1, 5, 10 or 30 minutes under Meeting notes. Longer speech is processed in chunks rather than repeatedly transcribing the whole recording. Meeting recording stops after two hours. File transcription supports audio formats Windows/NAudio can decode, including WAV, MP3, M4A, FLAC and WMA.

Local timers, workspaces and other instant commands do not require an AI request. Reminders are delivered while Atticus runs; overdue items fire after restart. Windows notification settings may suppress the banner, but due items remain visible. Background workers stop with the app and abandoned jobs are marked interrupted on restart; they are not silently replayed.

## Setup and development

Requires Windows 10 2004 or newer, Python 3.11+, .NET 10 SDK, Git and a native Codex CLI installation. Install/sign in to Codex separately. A currently supported CLI is required; the adapter uses the experimental app-server dynamic tool protocol.

```powershell
codex login
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` installs for the current user, creates a Start menu shortcut, enables login startup unless disabled in Settings, and launches the app. `install.ps1` downloads this Codex edition into a separate `.atticus-codex` source folder. Existing local checkouts can use `build.ps1` directly.

Installed app: `%LOCALAPPDATA%\Programs\Atticus`. Python and the speech model: `%LOCALAPPDATA%\Atticus`. Settings/history: `%APPDATA%\Atticus`.

Set `provider` to `codex` in settings. The desktop defaults to Codex; the Python engine retains the upstream Claude adapter for regression compatibility. `codexEffort` is `low`, `medium` or `high`. `codexModel`, if set, explicitly overrides model selection; otherwise the adapter selects the default advertised by `model/list`, avoiding an incompatible global model setting. `ATTICUS_CODEX` can override native CLI discovery.

Codex prepares its connection and tool context while you speak or type. Preparation does not start an AI turn or execute tools. A compact provider-specific prompt avoids unused shell instructions; typed questions capture screens only when they refer to screen content. Remote model load and network latency can still affect response time.

## Tools, privacy and approvals

`codex_provider.py` supplies structured dynamic tools: `atticus_action`, `atticus_service` and `atticus_mcp`. Desktop helpers use an allowlist and argument arrays. Built-in shell tools and inherited desktop plugins are excluded. Codex itself has a read-only sandbox; approved helpers, saved commands and local MCP servers run as the current Windows user outside that sandbox. This is an approval boundary, not full desktop isolation.

Read helpers include search, page reading, window enumeration, screen capture and clipboard reading. Other desktop helpers require Atticus's Allow card when Safe mode is on. Tool calls always wait for the transcript to be confirmed. Unknown requests fail closed. The model cannot grant itself a folder, save its own executable commands or configure its own MCP server. Existing instant commands remain local. Automatic learning of new executable shell shortcuts from Codex tool calls is disabled.

Project file access is limited to selected folders and UTF-8 text. Traversal, escaping symlinks, common credential files, source-control internals and dependency directories are excluded. Reads are bounded to 2 MB and return at most 40,000 characters; proposed content is bounded to 500 KB. This protects responsiveness; large changes should be split into files/steps. Builds are explicitly saved command arrays and have a 30-minute timeout. They can access anything your Windows account can access, so review the executable and arguments.

MCP supports local stdio servers (`command`, `args`, optional `env_vars`) and Streamable HTTP (`url`, optional `bearer_token_env_var`). It does not import Codex's configured servers. Credentials are referenced by environment variable name, not pasted into the server JSON. OAuth sign-in and interactive server requests are not implemented; authenticate/configure the server separately. Third-party services retain their own permissions, charges and limits.

Optional `server_options` supports only local Blender host/port, IntelliJ MCP port and telemetry preferences; credentials must still be environment-variable references. Windows system environment variables are preserved for socket/crypto startup without inheriting unrelated account tokens. Stateful MCP clients remain alive throughout one Codex task, so browser navigation and subsequent inspection share the same session; the owned processes are closed when the task ends.

`personal_mcp.py` provides read-only GitHub tools using the existing GitHub CLI login, Outlook mail/calendar through an existing local classic Outlook profile, and access to a local OneDrive sync folder. It does not send mail, create appointments or publish changes. Outlook data is passed through JSON stdin to a fixed PowerShell adapter. OneDrive support covers locally synced files, not every cloud-only Drive/SharePoint location. These local sessions are separate from Codex's connected cloud apps.

OAuth services can use an explicitly configured external `mcp-remote` stdio proxy. The user completes sign-in in their browser; Atticus does not copy Codex OAuth tokens or submit passwords. Prepared Figma/Render definitions require that sign-in before they are usable. A discovered tool catalogue alone does not prove that a target editor is open or its account authorisation is complete; the control centre displays connection status.

The provider starts an ephemeral session with a temporary isolated Codex home. On NTFS it hard-links the current user's existing `auth.json` for the lifetime of the request, without copying credential contents into the repository or application settings. Temporary request folders are removed on normal exit. Credential-manager-only sign-ins and cross-volume hard links are not supported by this adapter. If Codex rotates authentication inside a request and a later request needs sign-in, run `codex login` again.

Audio remains local. Text, attached screen images and helper results may be sent to Codex. Meeting transcripts are saved locally and sent only when a summary is requested. System/microphone labels identify channels, not individual speakers; this is recorded-note transcription, not live speaker diarisation. Recording audio is deleted after transcription on normal completion; an abrupt process/PC shutdown can leave temporary recording files under `%LOCALAPPDATA%\Atticus\recording-*`. Dollar cost is unavailable and is labelled accordingly. No new OpenAI API key is required for the existing ChatGPT sign-in.

Runtime reminders, folder grants, command definitions and jobs live in `%APPDATA%\Atticus\assistant.json`. Backups, job output and meeting transcripts are also stored there, outside the repository. Keep those private. Permissions are per Windows user, not a multi-user security boundary.

## Practical boundaries

These features reduce earlier restrictions; they cannot make the assistant unlimited or infallible. Hosted Codex needs connectivity and account capacity. Applications may expose incomplete controls, refuse window positions or require manual sign-in/elevation. Project tools do not support arbitrary binary editing. Speech recognition and model answers can be wrong. A helper executing does not prove the requested result happened: receipts explicitly distinguish observed results from unverified execution. Review consequential actions and meeting transcripts.

Keep automatic updates off for this local adaptation so the upstream installer cannot replace it. Local modifications also cause the updater to skip updates.

## Checks

```powershell
$env:PYTHONUTF8 = '1'
python -m unittest discover -s tests -v
python atticus.py --selftest
```

Use a scratch `ATTICUS_DIR` for tests and diagnostic requests. After building, run the installed `Atticus.exe --selftest`. Transport/tool tests in `tests/test_codex_provider.py` cover invalid helpers, transcript confirmation, declined approvals, argument handling and unknown server requests.

Serve the repository on loopback and open `tests/ui.html` and `tests/hub.html` for browser regressions. The overlay timing tests need a foreground tab because browsers throttle background timers. Close the test tabs/browser afterwards. `tests/test_assistant_services.py` additionally covers Windows lock contention, project preview/backups/conflicts, reminder delivery, workspace verification, real worker completion/cancellation, recovery and MCP stdio/HTTP fixtures. `Atticus.exe --transcribe-file <audio-path>` exercises the same resampling/chunking path used for meeting files without starting recording.

`Atticus.exe --meeting-capture-test <speech-fixture.wav>` plays a local speech fixture, records actual system loopback through the same recorder as meetings, downmixes multichannel output, and transcribes it. It briefly opens the microphone device but discards its samples; no microphone audio is saved. Generated capture files are removed afterwards. Use only when a short audio-output test is appropriate and unrelated media is stopped.

## Source

- `win/Atticus/`: C# tray app, WebView2 interfaces, microphone, hotkeys and local speech.
- `atticus.py`: commands, routing, history and desktop orchestration.
- `codex_provider.py`: Codex discovery, authentication check, app-server JSONL transport and approved helper boundary.
- `assistant_services.py`: persistent local services, grants, file previews/backups and background workers.
- `mcp_bridge.py`: explicit stdio/Streamable HTTP MCP clients.
- `winctl.py`: Windows automation.
- `ui/`: overlay, onboarding and settings.
- `integrations/`: service adapters.

## Ownership and licences

Copyright (c) 2026 Atticus Codex Maintainer, for original protectable additions and modifications only. All rights reserved in those contributions where applicable; see [LICENSE-ADDITIONS.txt](LICENSE-ADDITIONS.txt). Public source availability is not a general redistribution licence for those contributions.

Upstream Atticus remains MIT-licensed under [LICENSE](LICENSE). Its authors retain their rights. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for source provenance, the thinking-orbs MIT notice and dependency information, and [OWNERSHIP.md](OWNERSHIP.md) for the ownership/publication record. No affiliation, endorsement, trademark registration or exclusive ownership of upstream code is claimed.
