# Screenshot to Terminal

A Windows tray utility built for the **AI / vibe-coding workflow**:
capture → save → path-in-clipboard → paste straight into Claude Code / ChatGPT / any LLM chat.

Bonus: a one-key OCR mode replaces the image in your clipboard with the recognized text — often cheaper (fewer tokens) and more accurate than letting the model read the screenshot itself.

---

## Why?

Existing tools (ShareX, Greenshot, Snipping Tool) are great at capture, but they don't *connect* to LLM chats. The standard workflow looks like this:

1. `Win+Shift+S` — clip a region, image lands in clipboard
2. Now where do you paste it? You can't paste an image into a terminal
3. Open Paint, paste, save, copy the path, paste the path into your terminal

Five steps. Every screenshot. All day.

With this tool:

1. `Ctrl+Alt+A` — drag a box around the error
2. Switch to Claude Code in your terminal
3. `Ctrl+V` — path appears, Claude reads the image automatically

Or use `Ctrl+Alt+D` to send pure text via OCR — saves tokens, avoids the model misreading the screenshot.

---

## Features

- **Three capture modes**, all routed to the same `~/Pictures/Screenshots` folder:
  - `Ctrl+Alt+S` — save the clipboard image via a Save-As dialog (with the filename pre-selected so you can type a new name right away)
  - `Ctrl+Alt+Shift+S` — same, but instant — no dialog
  - `Ctrl+Alt+A` — built-in area selector with a Snipping-Tool-style spotlight overlay
- **`Ctrl+Alt+D` — OCR** the clipboard image to text using Windows.Media.Ocr (offline, multi-language). Picks the engine automatically from the language packs you have installed, then keeps whichever result actually reads like that language — so Russian text no longer comes back transliterated as `nepe3anyu.1e1-l`
- **Rebindable hotkeys** — change any of the four from the tray menu, no source editing
- **Auto-delete old screenshots** — off by default; 7 / 30 / 90 days available from the tray. Only touches files this app created, never anything else in the folder
- **Dual-format clipboard**: every save puts both the image AND its file path into the clipboard simultaneously. Paste into a terminal → get the path. Paste into Paint → get the image.
- **PNG or JPEG** — saves as PNG by default; switch to JPEG anytime from the tray menu (**Save format**)
- **Custom filename prefix** per project — set `bugfix-auth` and your shots become `bugfix-auth_2026-05-18_14-22-01.png`
- **Auto-resize** large screenshots down to 1920 px on the longest side (saves tokens and disk)
- **10-language UI** — English, Русский, 中文, 日本語, Deutsch, Italiano, Español, Français, Português, 한국어 (switch from the tray menu)
- **Remembers last-used folder**, runs in system tray, single-instance protection, one-click autostart toggle

---

## Install

### Ready-made build (no Python)

Grab the latest `ScreenshotToTerminal-*-win64.zip` from [Releases](https://github.com/dimabaluev-source/screenshot-to-terminal/releases), unzip anywhere, run `ScreenshotToTerminal.exe`. OCR still needs Windows language packs — see [INSTALL_OCR.md](INSTALL_OCR.md).

### From source

Requirements: **Windows 10/11**, **Python 3.10+**.

```powershell
git clone https://github.com/dimabaluev-source/screenshot-to-terminal.git
cd screenshot-to-terminal
pip install -r requirements.txt
pythonw screenshot_to_terminal.pyw
```

A blue **S** icon appears in the tray within a second.

> Note: `winsdk` compiles native bindings on first install — expect a few minutes.

### Add OCR language packs (needed for `Ctrl+Alt+D`)

The Windows OCR engine only recognizes languages you've installed at the OS level. See [INSTALL_OCR.md](INSTALL_OCR.md) for step-by-step instructions.

### Build a standalone .exe (optional)

```
build.bat
```

Produces `dist\ScreenshotToTerminal\ScreenshotToTerminal.exe` — drop the folder anywhere, no Python required.

---

## Hotkeys

| Hotkey               | Action                                                           |
|----------------------|------------------------------------------------------------------|
| `Ctrl+Alt+S`         | Save clipboard image — Save-As dialog                            |
| `Ctrl+Alt+Shift+S`   | Save clipboard image instantly to `~/Pictures/Screenshots`       |
| `Ctrl+Alt+A`         | Area selector (spotlight overlay) → save instantly               |
| `Ctrl+Alt+D`         | OCR the clipboard image, replace clipboard with recognized text  |

Typical flow: use the built-in **`Win+Shift+S`** to copy a region to clipboard, then trigger one of the hotkeys above. Or skip `Win+Shift+S` entirely and just use `Ctrl+Alt+A`.

All four are rebindable from the tray menu (**Hotkeys**) — type a combination like `ctrl+alt+q`. If another app already registered it, you get a warning, but the binding still applies: the low-level hook sees keys before the other app does.

---

## Tray menu

Right-click the blue **S** icon:

- **Hotkeys** — rebind any of the four capture actions
- **Filename prefix** — per-project tagging (e.g. `bugfix-auth`)
- **Save format** — choose **PNG** (default) or **JPEG**
- **Delete old screenshots** — never (default) / 7 / 30 / 90 days
- **Auto-resize toggle** — on/off
- **Autostart with Windows** — uses `HKCU\...\Run`, fully reversible
- **Language** — 10 UI languages: English, Русский, 中文, 日本語, Deutsch, Italiano, Español, Français, Português, 한국어 _(UI only — OCR languages depend on your installed Windows packs)_
- **Open screenshots folder** / **Open error log**
- **Exit** — the proper way to shut down (don't use Task Manager)

---

## Configuration

Everything set from the tray persists in `%APPDATA%\screenshot_to_terminal\config.json`. A few keys have no UI and can be set by hand (restart afterwards):

| Key | Meaning |
|---|---|
| `hotkeys` | `{"dialog": "ctrl+alt+s", "quick": …, "area": …, "ocr": …}` — normally written by the tray menu |
| `ocr_languages` | Force specific OCR engines, e.g. `["ja", "en-US"]`. Omit to auto-pick by UI language |
| `cleanup_days` | `0` = never delete; otherwise age in days |
| `debug_log` | `true` writes raw OCR output to the log — off by default so the log stays a log |

The constants at the top of `screenshot_to_terminal.pyw` (`HOTKEY_DIALOG` and friends) are only the defaults used until you change them in the tray.

---

## Known limitations

- **Windows-only.** Uses Win32, Windows.Media.Ocr, and the Windows registry. No plans for Linux/macOS.
- **OCR needs language packs.** See [INSTALL_OCR.md](INSTALL_OCR.md). The app uses whatever is installed — it can't recognize a language Windows doesn't have.
- **Low-level keyboard hook.** The `keyboard` library hooks system-wide, so if another app is bound to the same combination, it silently loses its binding while this runs. Rebind from the tray if that's a problem.
- **Stuck-key state in the hook (handled, worth knowing).** `keyboard` matches a hotkey against the *exact* set of keys it believes are held, and it learns that set only from hook events. Release a modifier while focus sits somewhere the hook can't see — an elevated window, a UAC prompt, the lock screen, a fullscreen game — and the KEY_UP never arrives: that key stays "held" forever and **every** hotkey stops firing, silently, until restart. This is the classic "it worked for days, then quit" failure of hook-based tools. A watchdog thread now reconciles that set against real key state (`GetAsyncKeyState`) every 2 seconds and drops the phantoms; when it fires it logs `watchdog: сняты залипшие клавиши [...]`.
- **Conflict detection is one-sided.** The warning when you assign a taken hotkey uses `RegisterHotKey`, so it only sees apps that register properly. Other hook-based utilities are invisible to it — and to each other.
- **Mixed-DPI multi-monitor.** Supported via `PER_MONITOR_AWARE`, but very exotic configurations may glitch the area selector.

---

## Contributing

Issues and PRs welcome. The whole point of this project is that you can read the entire script in one sitting and fork it for your own setup — please keep it single-file and dependency-light.

Good areas for contribution:
- Capture history (re-copy path of one of last N screenshots from tray menu)
- Blur/redact a region before saving — screenshots go to third-party models, and tokens or client names sometimes ride along
- A direct "send to Claude/ChatGPT" mode using a URL handler
- Cross-platform port (would likely become a sibling project)

---

## License

MIT — see [LICENSE](LICENSE).
