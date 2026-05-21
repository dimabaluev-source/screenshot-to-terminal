# Screenshot to Terminal

A Windows tray utility built for the **AI / vibe-coding workflow**:
capture → save → path-in-clipboard → paste straight into Claude Code / ChatGPT / any LLM chat.

Bonus: a one-key OCR mode replaces the image in your clipboard with the recognized text — often cheaper (fewer tokens) and more accurate than letting the model read the screenshot itself.

![Demo](assets/demo.gif)
> _Replace with your own demo GIF after first run._

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
- **`Ctrl+Alt+D` — OCR** the clipboard image to text using Windows.Media.Ocr (offline, multi-language)
- **Dual-format clipboard**: every save puts both the image AND its file path into the clipboard simultaneously. Paste into a terminal → get the path. Paste into Paint → get the image.
- **PNG or JPEG** — saves as PNG by default; switch to JPEG anytime from the tray menu (**Save format**)
- **Custom filename prefix** per project — set `bugfix-auth` and your shots become `bugfix-auth_2026-05-18_14-22-01.png`
- **Auto-resize** large screenshots down to 1920 px on the longest side (saves tokens and disk)
- **Remembers last-used folder**, runs in system tray, single-instance protection, one-click autostart toggle

---

## Install (from source)

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

---

## Tray menu

Right-click the blue **S** icon:

- **Filename prefix** — per-project tagging (e.g. `bugfix-auth`)
- **Save format** — choose **PNG** (default) or **JPEG**
- **Auto-resize toggle** — on/off
- **Autostart with Windows** — uses `HKCU\...\Run`, fully reversible
- **Language** — English / Русский
- **Open screenshots folder** / **Open error log**
- **Exit** — the proper way to shut down (don't use Task Manager)

---

## Configuration

All settings persist in `%APPDATA%\screenshot_to_terminal\config.json`. Edit it manually if you want to override defaults; restart the app afterwards.

To change the hotkeys, edit these constants at the top of `screenshot_to_terminal.pyw`:

```python
HOTKEY_DIALOG = 'ctrl+alt+s'
HOTKEY_QUICK  = 'ctrl+alt+shift+s'
HOTKEY_AREA   = 'ctrl+alt+a'
HOTKEY_OCR    = 'ctrl+alt+d'
```

---

## Known limitations

- **Windows-only.** Uses Win32, Windows.Media.Ocr, and the Windows registry. No plans for Linux/macOS.
- **OCR needs language packs.** See [INSTALL_OCR.md](INSTALL_OCR.md).
- **Low-level keyboard hook.** The `keyboard` library hooks system-wide. If another app is bound to the same hotkey, it will lose its binding silently while this script runs. Change hotkeys in the script if that's a problem.
- **Mixed-DPI multi-monitor.** Supported via `PER_MONITOR_AWARE`, but very exotic configurations may glitch the area selector.

---

## Contributing

Issues and PRs welcome. The whole point of this project is that you can read the entire script in one sitting and fork it for your own setup — please keep it single-file and dependency-light.

Good areas for contribution:
- More OCR language presets
- Capture history (re-copy path of one of last N screenshots from tray menu)
- A direct "send to Claude/ChatGPT" mode using a URL handler
- Cross-platform port (would likely become a sibling project)

---

## License

MIT — see [LICENSE](LICENSE).
