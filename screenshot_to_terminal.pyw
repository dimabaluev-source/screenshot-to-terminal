import os
import io
import sys
import time
import json
import queue
import asyncio
import threading
import ctypes
import winreg
import keyboard
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageEnhance, ImageTk
import win32clipboard
import win32con
import win32event
import win32api
import winerror
import tkinter as tk
from tkinter import filedialog, simpledialog

from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.globalization import Language
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream


# ============================================================
# Конфигурация
# ============================================================
DEFAULT_SCREENSHOTS_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")
APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "screenshot_to_terminal")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
LOG_FILE = os.path.join(APP_DATA_DIR, "error.log")

HOTKEY_DIALOG = 'ctrl+alt+s'
HOTKEY_QUICK = 'ctrl+alt+shift+s'
HOTKEY_AREA = 'ctrl+alt+a'
HOTKEY_OCR = 'ctrl+alt+d'

OCR_LANGUAGES = ('ru-RU', 'en-US')

MUTEX_NAME = "ScreenshotToTerminal_SingleInstance_Mutex"
APP_TITLE = "Screenshot to Terminal"

MAX_DIMENSION = 1920  # auto-resize: longest side won't exceed this
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "ScreenshotToTerminal"


# ============================================================
# Глобальное состояние
# ============================================================
stop_event = threading.Event()
action_queue: "queue.Queue[str]" = queue.Queue()
icon_ref = None
_mutex_handle = None
_config_cache = None


# ============================================================
# Конфиг
# ============================================================
def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _config_cache = json.load(f) or {}
        except Exception:
            _config_cache = {}
    return _config_cache


def _save_config() -> None:
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_config_cache or {}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"save_config: {e}")


def get_config(key: str, default):
    return _load_config().get(key, default)


def set_config(key: str, value) -> None:
    cfg = _load_config()
    cfg[key] = value
    _save_config()


# ============================================================
# Утилиты
# ============================================================
def log_error(msg: str) -> None:
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def notify(message: str) -> None:
    if icon_ref is not None:
        try:
            icon_ref.notify(message, APP_TITLE)
        except Exception as e:
            log_error(f"notify: {e}")


def load_last_dir() -> str:
    path = get_config("last_dir", DEFAULT_SCREENSHOTS_DIR)
    return path if isinstance(path, str) and path else DEFAULT_SCREENSHOTS_DIR


def save_last_dir(path: str) -> None:
    set_config("last_dir", path)


def clipboard_has_image() -> bool:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                return bool(win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB))
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    return False


def set_clipboard_text(text: str) -> None:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    log_error("set_clipboard_text: failed after retries")


def _pil_to_dib_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.convert('RGB').save(output, 'BMP')
    # CF_DIB не включает 14-байтовый BITMAPFILEHEADER
    return output.getvalue()[14:]


def set_clipboard_image_and_text(image: Image.Image, text: str) -> None:
    """Кладёт в буфер обмена и изображение (CF_DIB), и текст (CF_UNICODETEXT)."""
    try:
        dib = _pil_to_dib_bytes(image)
    except Exception as e:
        log_error(f"pil_to_dib: {e}")
        set_clipboard_text(text)
        return

    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    log_error("set_clipboard_image_and_text: failed after retries")


# ============================================================
# Авторесайз и сохранение
# ============================================================
def _maybe_resize(image: Image.Image) -> Image.Image:
    if not get_config("auto_resize", True):
        return image
    w, h = image.size
    longest = max(w, h)
    if longest <= MAX_DIMENSION:
        return image
    scale = MAX_DIMENSION / longest
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _sanitize_prefix(s: str) -> str:
    if not s:
        return ""
    # Запрещённые в Windows-именах символы
    forbidden = '\\/:*?"<>|\t\r\n'
    cleaned = ''.join(c for c in s if c not in forbidden).strip().strip('.')
    return cleaned[:60]


def _generate_filename(extension: str = ".jpeg") -> str:
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    prefix = _sanitize_prefix(get_config("filename_prefix", "") or "")
    base = prefix if prefix else "Снимок"
    return f"{base}_{timestamp}{extension}"


def _save_image(image: Image.Image, filepath: str) -> Image.Image:
    """Сохраняет файл и возвращает финальную (после ресайза/конвертации) картинку."""
    image = _maybe_resize(image)
    ext = os.path.splitext(filepath)[1].lower()
    if image.mode == 'RGBA' and ext != '.png':
        image = image.convert('RGB')
    if ext == '.png':
        image.save(filepath, "PNG", optimize=True)
    else:
        image.save(filepath, "JPEG", quality=95, optimize=True, subsampling=0)
    return image


def save_screenshot_with_dialog() -> None:
    if not clipboard_has_image():
        notify("В буфере нет картинки")
        return

    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return

        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        last_dir = load_last_dir()
        if not os.path.isdir(last_dir):
            last_dir = DEFAULT_SCREENSHOTS_DIR

        initial_filename = _generate_filename(".jpeg")

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        def select_filename_in_dialog():
            time.sleep(0.35)
            try:
                keyboard.send('ctrl+a')
            except Exception as e:
                log_error(f"select_filename: {e}")

        threading.Thread(target=select_filename_in_dialog, daemon=True).start()

        try:
            filepath = filedialog.asksaveasfilename(
                title="Сохранить скриншот как...",
                initialdir=last_dir,
                initialfile=initial_filename,
                defaultextension=".jpeg",
                filetypes=[("JPEG Image", "*.jpeg"), ("PNG Image", "*.png"), ("All files", "*.*")]
            )
        finally:
            try:
                root.destroy()
            except Exception:
                pass

        if not filepath:
            return

        saved = _save_image(image, filepath)
        save_last_dir(os.path.dirname(filepath))
        set_clipboard_image_and_text(saved, filepath)
        notify(f"Сохранено: {os.path.basename(filepath)}")
    except Exception as e:
        log_error(f"save_screenshot_with_dialog: {e}")


def save_screenshot_quick() -> None:
    if not clipboard_has_image():
        notify("В буфере нет картинки")
        return

    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return

        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        filename = _generate_filename(".jpeg")
        filepath = os.path.join(DEFAULT_SCREENSHOTS_DIR, filename)

        saved = _save_image(image, filepath)
        set_clipboard_image_and_text(saved, filepath)
        notify(f"Быстро сохранено: {filename}")
    except Exception as e:
        log_error(f"save_screenshot_quick: {e}")


# ============================================================
# Захват области экрана через overlay
# ============================================================
def _capture_screen_area_bbox():
    """Spotlight-overlay: затемняем экран, область под курсором — без затемнения. Возвращает (x1, y1, x2, y2) или None."""
    user32 = ctypes.windll.user32
    virtual_x = user32.GetSystemMetrics(76)
    virtual_y = user32.GetSystemMetrics(77)
    virtual_w = user32.GetSystemMetrics(78)
    virtual_h = user32.GetSystemMetrics(79)

    # Захватываем экран ДО показа overlay, чтобы overlay сам не попал в кадр
    bright = ImageGrab.grab(
        bbox=(virtual_x, virtual_y, virtual_x + virtual_w, virtual_y + virtual_h),
        all_screens=True,
    )
    dim = ImageEnhance.Brightness(bright).enhance(0.5)

    root = tk.Tk()
    root.attributes('-topmost', True)
    root.overrideredirect(True)
    root.geometry(f"{virtual_w}x{virtual_h}+{virtual_x}+{virtual_y}")
    root.configure(cursor='crosshair')

    canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0)
    canvas.pack(fill='both', expand=True)

    dim_tk = ImageTk.PhotoImage(dim)
    canvas.create_image(0, 0, anchor='nw', image=dim_tk)
    # Держим ссылку, иначе сборщик уберёт изображение
    canvas._dim_ref = dim_tk

    state = {
        'start': None,        # (screen_x, screen_y) — глобальные координаты
        'bright_id': None,    # id яркого фрагмента в canvas
        'rect_id': None,      # id красной рамки
        'bright_tk': None,    # держим ссылку на PhotoImage
        'pending_after': None,
        'bbox': None,
    }

    def update_selection_canvas_coords(cx1, cy1, cx2, cy2):
        cx1, cx2 = sorted((cx1, cx2))
        cy1, cy2 = sorted((cy1, cy2))
        cx1 = max(0, min(virtual_w, cx1))
        cy1 = max(0, min(virtual_h, cy1))
        cx2 = max(0, min(virtual_w, cx2))
        cy2 = max(0, min(virtual_h, cy2))
        if cx2 - cx1 < 1 or cy2 - cy1 < 1:
            return

        if state['bright_id'] is not None:
            canvas.delete(state['bright_id'])
        if state['rect_id'] is not None:
            canvas.delete(state['rect_id'])

        cropped = bright.crop((cx1, cy1, cx2, cy2))
        state['bright_tk'] = ImageTk.PhotoImage(cropped)
        state['bright_id'] = canvas.create_image(
            cx1, cy1, anchor='nw', image=state['bright_tk']
        )
        state['rect_id'] = canvas.create_rectangle(
            cx1, cy1, cx2, cy2, outline='red', width=2
        )

    def schedule_update(x_root, y_root):
        # Throttle: пересчитываем не чаще ~30 fps
        if state['pending_after'] is not None:
            return
        sx, sy = state['start']
        cx1 = sx - virtual_x
        cy1 = sy - virtual_y
        cx2 = x_root - virtual_x
        cy2 = y_root - virtual_y

        def do_update():
            state['pending_after'] = None
            update_selection_canvas_coords(cx1, cy1, cx2, cy2)

        state['pending_after'] = canvas.after(30, do_update)

    def on_press(event):
        state['start'] = (event.x_root, event.y_root)

    def on_drag(event):
        if state['start']:
            schedule_update(event.x_root, event.y_root)

    def on_release(event):
        if state['start']:
            x1 = min(state['start'][0], event.x_root)
            y1 = min(state['start'][1], event.y_root)
            x2 = max(state['start'][0], event.x_root)
            y2 = max(state['start'][1], event.y_root)
            if (x2 - x1) > 5 and (y2 - y1) > 5:
                state['bbox'] = (x1, y1, x2, y2)
        try:
            root.destroy()
        except Exception:
            pass

    def on_escape(event):
        state['bbox'] = None
        try:
            root.destroy()
        except Exception:
            pass

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    root.bind('<Escape>', on_escape)

    root.mainloop()
    return state['bbox']


def save_screenshot_area() -> None:
    try:
        bbox = _capture_screen_area_bbox()
        if not bbox:
            return

        image = ImageGrab.grab(bbox=bbox, all_screens=True)
        if not isinstance(image, Image.Image):
            return

        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        filename = _generate_filename(".jpeg")
        filepath = os.path.join(DEFAULT_SCREENSHOTS_DIR, filename)

        saved = _save_image(image, filepath)
        set_clipboard_image_and_text(saved, filepath)
        notify(f"Область сохранена: {filename}")
    except Exception as e:
        log_error(f"save_screenshot_area: {e}")


# ============================================================
# OCR через Windows.Media.Ocr (без интернета)
# ============================================================
def _has_cyrillic(s: str) -> bool:
    return any('Ѐ' <= c <= 'ӿ' for c in s)


def _upscale_for_ocr(image: Image.Image, target_min_side: int = 1500) -> Image.Image:
    w, h = image.size
    longest = max(w, h)
    if longest >= target_min_side:
        return image
    scale = target_min_side / longest
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


async def _ocr_pil_image_async(pil_image: Image.Image) -> str:
    pil_image = _upscale_for_ocr(pil_image)

    buf = io.BytesIO()
    pil_image.save(buf, format='PNG')
    image_bytes = buf.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(image_bytes)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    results: dict = {}
    for tag in OCR_LANGUAGES:
        try:
            lang = Language(tag)
            if not OcrEngine.is_language_supported(lang):
                continue
            engine = OcrEngine.try_create_from_language(lang)
            if engine is None:
                continue
            result = await engine.recognize_async(bitmap)
            text = (result.text or "").strip()
            results[tag] = text
            preview = text[:80].replace('\n', ' ')
            log_error(f"ocr[{tag}] len={len(text)} | {preview}")
        except Exception as e:
            log_error(f"ocr engine {tag}: {e}")

    ru = results.get('ru-RU', '')
    en = results.get('en-US', '')

    # Если в русском результате есть кириллица — он точно подходит лучше:
    # английский движок попытается прочесть русский текст латиницей и выдаст мусор.
    if _has_cyrillic(ru):
        return ru
    # Иначе берём английский (для чисто латинских текстов он точнее).
    if en:
        return en
    # Фоллбэк — что есть.
    return ru


def ocr_pil_image(pil_image: Image.Image) -> str:
    return asyncio.run(_ocr_pil_image_async(pil_image))


def ocr_from_clipboard() -> None:
    if not clipboard_has_image():
        notify("В буфере нет картинки")
        return
    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return
        text = ocr_pil_image(image)
        if not text:
            notify("Текст не найден")
            return
        set_clipboard_text(text)
        preview = text[:60].replace('\n', ' ').replace('\r', ' ')
        if len(text) > 60:
            preview += '…'
        notify(f"OCR ({len(text)} симв.): {preview}")
    except Exception as e:
        log_error(f"ocr_from_clipboard: {e}")
        notify(f"Ошибка OCR: {e}")


# ============================================================
# Диалог префикса имени
# ============================================================
def show_prefix_dialog() -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        current = get_config("filename_prefix", "") or ""
        new_value = simpledialog.askstring(
            "Префикс имени скриншотов",
            "Префикс для имён файлов (пусто = вернуть 'Снимок'):",
            initialvalue=current,
            parent=root,
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if new_value is None:
        return  # пользователь нажал «Отмена»

    cleaned = _sanitize_prefix(new_value)
    set_config("filename_prefix", cleaned)
    if cleaned:
        notify(f"Префикс: {cleaned}_…")
    else:
        notify("Префикс сброшен")


# ============================================================
# Worker и горячие клавиши
# ============================================================
def on_hotkey_dialog():
    action_queue.put('dialog')


def on_hotkey_quick():
    action_queue.put('quick')


def on_hotkey_area():
    action_queue.put('area')


def on_hotkey_ocr():
    action_queue.put('ocr')


def worker_loop():
    while not stop_event.is_set():
        try:
            action = action_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if action == 'dialog':
            save_screenshot_with_dialog()
        elif action == 'quick':
            save_screenshot_quick()
        elif action == 'area':
            save_screenshot_area()
        elif action == 'ocr':
            ocr_from_clipboard()
        elif action == 'set_prefix':
            show_prefix_dialog()


# ============================================================
# Автозапуск через реестр HKCU\...\Run
# ============================================================
def _autostart_command() -> str:
    py = sys.executable
    # На всякий случай заменим python.exe на pythonw.exe (чтобы без консоли)
    pyw = py.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = py
    script = os.path.abspath(__file__)
    return f'"{pyw}" "{script}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return value == _autostart_command()
    except FileNotFoundError:
        return False
    except Exception as e:
        log_error(f"is_autostart_enabled: {e}")
        return False


def set_autostart(enabled: bool) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
    except Exception as e:
        log_error(f"set_autostart: {e}")


# ============================================================
# Иконка и меню
# ============================================================
def create_icon_image() -> Image.Image:
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, size - 2, size - 2),
                 fill=(40, 90, 180, 255),
                 outline=(255, 255, 255, 255), width=2)
    try:
        font = ImageFont.truetype("arialbd.ttf", 38)
    except Exception:
        font = ImageFont.load_default()
    draw.text((size // 2, size // 2 - 2), "S", fill="white", font=font, anchor="mm")
    return img


def menu_open_screenshots(icon, item):
    try:
        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        os.startfile(DEFAULT_SCREENSHOTS_DIR)
    except Exception as e:
        log_error(f"open_screenshots: {e}")


def menu_open_log(icon, item):
    try:
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            notify("Лог пуст — ошибок не было")
    except Exception as e:
        log_error(f"open_log: {e}")


def menu_toggle_resize(icon, item):
    new_value = not get_config("auto_resize", True)
    set_config("auto_resize", new_value)
    notify(f"Авторесайз: {'включён' if new_value else 'выключен'}")


def menu_set_prefix(icon, item):
    action_queue.put('set_prefix')


def _prefix_menu_text(item) -> str:
    p = get_config("filename_prefix", "") or ""
    if not p:
        return "Префикс имени: (нет)"
    shown = p if len(p) <= 25 else p[:22] + '…'
    return f"Префикс имени: {shown}"


def menu_toggle_autostart(icon, item):
    new_value = not is_autostart_enabled()
    set_autostart(new_value)
    notify(f"Автозапуск: {'включён' if new_value else 'выключен'}")


def menu_exit(icon, item):
    stop_event.set()
    try:
        keyboard.remove_all_hotkeys()
    except Exception:
        pass
    try:
        icon.stop()
    except Exception:
        pass


def build_menu():
    return pystray.Menu(
        pystray.MenuItem('Скриншот-хелпер', None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Ctrl+Alt+S — сохранить через диалог', None, enabled=False),
        pystray.MenuItem('Ctrl+Alt+Shift+S — быстро в Pictures\\Screenshots', None, enabled=False),
        pystray.MenuItem('Ctrl+Alt+A — захват области экрана', None, enabled=False),
        pystray.MenuItem('Ctrl+Alt+D — OCR (текст из картинки в буфере)', None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_prefix_menu_text, menu_set_prefix),
        pystray.MenuItem(
            f'Авторесайз больших (>{MAX_DIMENSION}px)',
            menu_toggle_resize,
            checked=lambda item: get_config("auto_resize", True),
        ),
        pystray.MenuItem(
            'Автозапуск с Windows',
            menu_toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Открыть папку скриншотов', menu_open_screenshots, default=True),
        pystray.MenuItem('Открыть лог ошибок', menu_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Выход', menu_exit),
    )


# ============================================================
# Точка входа
# ============================================================
def main() -> None:
    global icon_ref, _mutex_handle

    # DPI-awareness для корректных координат overlay на high-DPI экранах
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # Защита от двойного запуска
    _mutex_handle = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Скриншот-хелпер уже запущен — посмотри иконку в трее.",
            APP_TITLE,
            0x40,
        )
        sys.exit(0)

    try:
        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
    except Exception as e:
        log_error(f"main mkdir: {e}")

    keyboard.add_hotkey(HOTKEY_DIALOG, on_hotkey_dialog)
    keyboard.add_hotkey(HOTKEY_QUICK, on_hotkey_quick)
    keyboard.add_hotkey(HOTKEY_AREA, on_hotkey_area)
    keyboard.add_hotkey(HOTKEY_OCR, on_hotkey_ocr)

    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()

    icon_ref = pystray.Icon(
        "screenshot_to_terminal",
        create_icon_image(),
        APP_TITLE,
        menu=build_menu(),
    )

    icon_ref.run()

    stop_event.set()
    worker_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
