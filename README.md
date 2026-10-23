# Atticus for Windows — Codex edition

Independent source-available adaptation of [FindlayHi/atticus-windows](https://github.com/FindlayHi/atticus-windows), originally [SaarthurR/atticus-mac](https://github.com/SaarthurR/atticus-mac).

Atticus is a Windows tray assistant. Hold **Ctrl+Alt+Space**, speak, then release. Speech is transcribed locally with Whisper. Questions and approved desktop actions use the **Codex CLI app-server**, signed in with your existing Codex account. Account limits apply. Esc cancels.

## Setup and development

Requires Windows 10 2004 or newer, Python 3.11+, .NET 10 SDK, Git and a native Codex CLI installation. Install/sign in to Codex separately. A currently supported CLI is required; the adapter uses the experimental app-server dynamic tool protocol.

```powershell
codex login
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` installs for the current user, creates a Start menu shortcut, enables login startup unless disabled in Settings, and launches the app. `install.ps1` downloads this Codex edition into a separate `.atticus-codex` source folder. Existing local checkouts can use `build.ps1` directly.

Installed app: `%LOCALAPPDATA%\Programs\Atticus`. Python and the speech model: `%LOCALAPPDATA%\Atticus`. Settings/history: `%APPDATA%\Atticus`.

Set `provider` to `codex` in settings. The desktop defaults to Codex; the Python engine retains the upstream Claude adapter for regression compatibility. `codexEffort` is `low`, `medium` or `high`. `codexModel`, if set, explicitly overrides model selection; otherwise the adapter selects the default advertised by `model/list`, avoiding an incompatible global model setting. `ATTICUS_CODEX` can override native CLI discovery.

## Tools, privacy and approvals

`codex_provider.py` supplies one structured dynamic tool, `atticus_action`. It runs an allowlist of Atticus helpers with argument arrays and no command shell. Built-in shell tools, inherited desktop plugins and MCP servers are excluded. Codex itself has a read-only sandbox; approved helpers run as the current user outside that sandbox. This is an approval boundary, not full desktop isolation.

Read helpers include search, page reading, window enumeration, screen capture and clipboard reading. Other helpers require Atticus's Allow card when Safe mode is on. Tool calls always wait for the transcript to be confirmed. Unknown requests fail closed. No arbitrary shell shortcuts, shell-based watchers or custom MCP servers are available in Codex mode. Existing instant commands remain local. Built-in HTTP integrations can be reached through the approved integration helper. Automatic learning of new executable shell shortcuts from Codex tool calls is disabled.

The provider starts an ephemeral session with a temporary isolated Codex home. On NTFS it hard-links the current user's existing `auth.json` for the lifetime of the request, without copying credential contents into the repository or application settings. Temporary request folders are removed on normal exit. Credential-manager-only sign-ins and cross-volume hard links are not supported by this adapter. If Codex rotates authentication inside a request and a later request needs sign-in, run `codex login` again.

Audio remains local. Text, attached screen images and helper results may be sent to Codex. Dollar cost is unavailable and is labelled accordingly; request counts and response times remain visible. No new OpenAI API key is required for the existing ChatGPT sign-in.

Keep automatic updates off for this local adaptation so the upstream installer cannot replace it. Local modifications also cause the updater to skip updates.

## Checks

```powershell
$env:PYTHONUTF8 = '1'
python -m unittest discover -s tests -v
python atticus.py --selftest
```

Use a scratch `ATTICUS_DIR` for tests and diagnostic requests. After building, run the installed `Atticus.exe --selftest`. Transport/tool tests in `tests/test_codex_provider.py` cover invalid helpers, transcript confirmation, declined approvals, argument handling and unknown server requests.

## Source

- `win/Atticus/`: C# tray app, WebView2 interfaces, microphone, hotkeys and local speech.
- `atticus.py`: commands, routing, history and desktop orchestration.
- `codex_provider.py`: Codex discovery, authentication check, app-server JSONL transport and approved helper boundary.
- `winctl.py`: Windows automation.
- `ui/`: overlay, onboarding and settings.
- `integrations/`: service adapters.

## Ownership and licences

Copyright (c) 2026 Atticus Codex Maintainer, for original protectable additions and modifications only. All rights reserved in those contributions where applicable; see [LICENSE-ADDITIONS.txt](LICENSE-ADDITIONS.txt). Public source availability is not a general redistribution licence for those contributions.

Upstream Atticus remains MIT-licensed under [LICENSE](LICENSE). Its authors retain their rights. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for source provenance, the thinking-orbs MIT notice and dependency information, and [OWNERSHIP.md](OWNERSHIP.md) for the ownership/publication record. No affiliation, endorsement, trademark registration or exclusive ownership of upstream code is claimed.
