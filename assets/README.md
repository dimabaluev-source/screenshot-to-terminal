# Assets

Drop screenshots and demo GIFs here so the main README can reference them.

Recommended files:

- **`demo.gif`** — 5–10 seconds, full workflow: `Win+Shift+S` → `Ctrl+Alt+D` → paste recognized text into a terminal. Or: `Ctrl+Alt+A` → draw box → paste path into Claude Code → model reads the file.
- **`tray-menu.png`** — right-click menu of the tray icon (shows the hotkey cheat-sheet)
- **`area-selector.png`** — spotlight overlay in action with a partial selection

## Recording a demo GIF on Windows

- [ScreenToGif](https://www.screentogif.com/) — free, open-source, exports GIF/MP4 directly. Recommended.
- Built-in **Snipping Tool** in Win11 can record short clips (MP4), then convert to GIF with ffmpeg:
  ```
  ffmpeg -i input.mp4 -vf "fps=15,scale=900:-1:flags=lanczos" -loop 0 demo.gif
  ```

Keep GIFs under ~3 MB so GitHub renders them inline without truncation.
