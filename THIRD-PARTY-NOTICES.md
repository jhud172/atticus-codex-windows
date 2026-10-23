# Attribution and third-party notices

This is an independent derivative edition. It is not an official product of OpenAI, Anthropic, Microsoft, or the upstream maintainers. Names and marks belong to their respective holders; no endorsement or trademark rights are claimed.

## Atticus upstream

- Original Mac project: [SaarthurR/atticus-mac](https://github.com/SaarthurR/atticus-mac), copyright (c) 2026 SaarthurR, MIT.
- Windows port: [FindlayHi/atticus-windows](https://github.com/FindlayHi/atticus-windows), MIT-licensed repository. Source baseline: `657cc26d9cac48ce6951958fc4b2b519787a0af6`.
- Preserve the complete upstream MIT licence in [LICENSE](LICENSE). Upstream source, UI and icons retain their existing rights and attribution.

The Codex provider, its tests, provider setup/model/usage changes and this edition's original documentation were added or modified after that baseline. Rights in original additions are described in [LICENSE-ADDITIONS.txt](LICENSE-ADDITIONS.txt).

## thinking-orbs

`ui/orbs.js` identifies thinking-orbs 0.3.2 by Jakub Antalik: https://github.com/Jakubantalik/thinking-orbs.

MIT License

Copyright (c) 2026 Jakub Antalik

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Installed dependencies

This source repository references packages including Whisper.net/whisper.cpp, NAudio, System.Speech, Microsoft.Web.WebView2, Pillow, mss, psutil and uiautomation. Codex CLI and the downloaded speech model are separate components. They are not relicensed by this edition. Their package licences and notices govern their use and redistribution.

The build installs dependencies rather than committing their binaries here. In particular, WebView2 has its own Microsoft redistribution licence and notices; do not assume every dependency is MIT. Binary distributors must carry the licences/notices required by their exact dependency versions.
