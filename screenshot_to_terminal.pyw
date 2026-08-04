import os
import io
import re
import sys
import time
import json
import queue
import asyncio
import threading
import ctypes
import winreg
import subprocess
import keyboard
from keyboard import _winkeyboard
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

# Значения по умолчанию — их можно переопределить из трея (Hotkeys),
# выбор сохраняется в config.json и переживает обновление скрипта.
HOTKEY_DIALOG = 'ctrl+alt+s'
HOTKEY_QUICK = 'ctrl+alt+shift+s'
HOTKEY_AREA = 'ctrl+alt+a'
HOTKEY_OCR = 'ctrl+alt+d'

HOTKEY_DEFAULTS = {
    'dialog': HOTKEY_DIALOG,
    'quick': HOTKEY_QUICK,
    'area': HOTKEY_AREA,
    'ocr': HOTKEY_OCR,
}

# Фоллбэк, если система почему-то не отдала список установленных движков OCR
OCR_LANGUAGES = ('en-US', 'ru')
MAX_OCR_ENGINES = 3  # каждый лишний движок — лишний прогон распознавания

# Лог: чтобы не рос бесконечно, при переполнении уезжает в .1
LOG_MAX_BYTES = 512 * 1024

# Автоудаление старых снимков (0 = выключено)
CLEANUP_CHOICES = (0, 7, 30, 90)
CLEANUP_INTERVAL = 6 * 3600
# Трогаем только файлы, которые сделала сама программа: prefix_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.ext
SCREENSHOT_NAME_RE = re.compile(
    r'^.+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.(png|jpe?g)$', re.IGNORECASE)

MUTEX_NAME = "ScreenshotToTerminal_SingleInstance_Mutex"
APP_TITLE = "Screenshot to Terminal"

# Перезапуск: старая копия поднимает новую с этим флагом, новая ждёт, пока
# освободится мьютекс, вместо того чтобы решить «уже запущен» и выйти.
RESTART_FLAG = "--restarted"
RESTART_WAIT = 10.0

# Самопроверка. Бывает, что процесс жив, хук на месте, а горячие клавиши молча
# перестают срабатывать — лечится только перезапуском (разбор 04.08.2026:
# события доходят до очереди keyboard, но обработчик хоткея не вызывается).
# Поэтому раз в минуту шлём себе безобидную клавишу и проверяем, что она прошла
# весь путь до обработчика. Не прошла дважды подряд — перезапускаемся.
HEARTBEAT_INTERVAL = 60.0
HEARTBEAT_TIMEOUT = 1.5
HEARTBEAT_FAILS_BEFORE_RESTART = 2
HEARTBEAT_VK = 0xFC             # VK_NONAME: ни одно приложение на неё не реагирует
HEARTBEAT_SCAN = -HEARTBEAT_VK  # keyboard хранит клавишу без скан-кода как -vk

DEFAULT_LANGUAGE = 'en'

I18N = {
    'en': {
        'lang.name': 'English',
        'notify.no_clipboard_image': 'Clipboard has no image',
        'notify.saved': 'Saved: {name}',
        'notify.quick_saved': 'Quick saved: {name}',
        'notify.area_saved': 'Area saved: {name}',
        'notify.no_text': 'No text found',
        'notify.ocr_result': 'OCR ({count} chars): {preview}',
        'notify.ocr_error': 'OCR error: {error}',
        'notify.prefix_set': 'Prefix: {prefix}_…',
        'notify.prefix_cleared': 'Prefix cleared',
        'notify.autoresize_on': 'Auto-resize: on',
        'notify.autoresize_off': 'Auto-resize: off',
        'notify.autostart_on': 'Autostart: on',
        'notify.autostart_off': 'Autostart: off',
        'notify.format_changed': 'Format: {fmt}',
        'notify.log_empty': 'Log is empty — no errors yet',
        'notify.language_changed': 'Language: English',
        'msg.already_running': 'Screenshot helper is already running — check the tray icon.',
        'dialog.save_title': 'Save screenshot as...',
        'dialog.prefix_title': 'Screenshot filename prefix',
        'dialog.prefix_prompt': "Filename prefix (empty = use default '{default}'):",
        'default.filename_base': 'Screenshot',
        'menu.title': 'Screenshot Helper',
        'menu.prefix_none': 'Filename prefix: (none)',
        'menu.prefix': 'Filename prefix: {value}',
        'menu.autoresize': 'Auto-resize large (>{px}px)',
        'menu.autostart': 'Autostart with Windows',
        'menu.format': 'Save format',
        'menu.open_folder': 'Open screenshots folder',
        'menu.open_log': 'Open error log',
        'menu.language': 'Language',
        'menu.restart': 'Restart',
        'notify.restart_failed': 'Could not restart',
        'menu.exit': 'Exit',
        'menu.hotkeys': 'Hotkeys',
        'action.dialog': 'Save via dialog',
        'action.quick': 'Quick save',
        'action.area': 'Capture area',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Change hotkey',
        'dialog.hotkey_prompt': 'Hotkey for "{action}".\nFor example: ctrl+alt+a',
        'notify.hotkey_set': 'Hotkey: {key}',
        'notify.hotkey_invalid': 'Not a valid hotkey: {key}',
        'notify.hotkey_conflict': '{key} is already taken by another app — it may not work',
        'notify.hotkey_failed': 'Could not bind {key}',
        'menu.cleanup': 'Delete old screenshots',
        'menu.cleanup_never': 'Never',
        'menu.cleanup_days': 'Older than {days} days',
        'notify.cleanup_on': 'Cleanup: older than {days} days (removed now: {count})',
        'notify.cleanup_off': 'Cleanup: off',
    },
    'ru': {
        'lang.name': 'Русский',
        'notify.no_clipboard_image': 'В буфере нет картинки',
        'notify.saved': 'Сохранено: {name}',
        'notify.quick_saved': 'Быстро сохранено: {name}',
        'notify.area_saved': 'Область сохранена: {name}',
        'notify.no_text': 'Текст не найден',
        'notify.ocr_result': 'OCR ({count} симв.): {preview}',
        'notify.ocr_error': 'Ошибка OCR: {error}',
        'notify.prefix_set': 'Префикс: {prefix}_…',
        'notify.prefix_cleared': 'Префикс сброшен',
        'notify.autoresize_on': 'Авторесайз: включён',
        'notify.autoresize_off': 'Авторесайз: выключен',
        'notify.autostart_on': 'Автозапуск: включён',
        'notify.autostart_off': 'Автозапуск: выключен',
        'notify.format_changed': 'Формат: {fmt}',
        'notify.log_empty': 'Лог пуст — ошибок не было',
        'notify.language_changed': 'Язык: Русский',
        'msg.already_running': 'Скриншот-хелпер уже запущен — посмотри иконку в трее.',
        'dialog.save_title': 'Сохранить скриншот как...',
        'dialog.prefix_title': 'Префикс имени скриншотов',
        'dialog.prefix_prompt': "Префикс для имён файлов (пусто = вернуть '{default}'):",
        'default.filename_base': 'Снимок',
        'menu.title': 'Скриншот-хелпер',
        'menu.prefix_none': 'Префикс имени: (нет)',
        'menu.prefix': 'Префикс имени: {value}',
        'menu.autoresize': 'Авторесайз больших (>{px}px)',
        'menu.autostart': 'Автозапуск с Windows',
        'menu.format': 'Формат сохранения',
        'menu.open_folder': 'Открыть папку скриншотов',
        'menu.open_log': 'Открыть лог ошибок',
        'menu.language': 'Язык',
        'menu.restart': 'Перезапустить',
        'notify.restart_failed': 'Не удалось перезапустить',
        'menu.exit': 'Выход',
        'menu.hotkeys': 'Горячие клавиши',
        'action.dialog': 'Сохранить через диалог',
        'action.quick': 'Быстрое сохранение',
        'action.area': 'Захват области',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Смена горячей клавиши',
        'dialog.hotkey_prompt': 'Комбинация для «{action}».\nНапример: ctrl+alt+a',
        'notify.hotkey_set': 'Горячая клавиша: {key}',
        'notify.hotkey_invalid': 'Не похоже на комбинацию: {key}',
        'notify.hotkey_conflict': '{key} уже занята другой программой — может не сработать',
        'notify.hotkey_failed': 'Не удалось назначить {key}',
        'menu.cleanup': 'Удалять старые снимки',
        'menu.cleanup_never': 'Никогда',
        'menu.cleanup_days': 'Старше {days} дней',
        'notify.cleanup_on': 'Очистка: старше {days} дней (удалено сейчас: {count})',
        'notify.cleanup_off': 'Очистка: выключена',
    },
    'zh': {
        'lang.name': '中文',
        'notify.no_clipboard_image': '剪贴板中没有图片',
        'notify.saved': '已保存：{name}',
        'notify.quick_saved': '已快速保存：{name}',
        'notify.area_saved': '已保存区域：{name}',
        'notify.no_text': '未找到文本',
        'notify.ocr_result': 'OCR（{count} 个字符）：{preview}',
        'notify.ocr_error': 'OCR 错误：{error}',
        'notify.prefix_set': '前缀：{prefix}_…',
        'notify.prefix_cleared': '前缀已清除',
        'notify.autoresize_on': '自动缩放：开',
        'notify.autoresize_off': '自动缩放：关',
        'notify.autostart_on': '开机自启：开',
        'notify.autostart_off': '开机自启：关',
        'notify.format_changed': '格式：{fmt}',
        'notify.log_empty': '日志为空 — 暂无错误',
        'notify.language_changed': '语言：中文',
        'msg.already_running': '截图助手已在运行 — 请查看托盘图标。',
        'dialog.save_title': '截图另存为...',
        'dialog.prefix_title': '截图文件名前缀',
        'dialog.prefix_prompt': "文件名前缀（留空 = 使用默认 '{default}'）：",
        'default.filename_base': '截图',
        'menu.title': '截图助手',
        'menu.prefix_none': '文件名前缀：（无）',
        'menu.prefix': '文件名前缀：{value}',
        'menu.autoresize': '自动缩放大图（>{px}px）',
        'menu.autostart': '开机自启动',
        'menu.format': '保存格式',
        'menu.open_folder': '打开截图文件夹',
        'menu.open_log': '打开错误日志',
        'menu.language': '语言',
        'menu.restart': '重启',
        'notify.restart_failed': '无法重启',
        'menu.exit': '退出',
        'menu.hotkeys': '快捷键',
        'action.dialog': '通过对话框保存',
        'action.quick': '快速保存',
        'action.area': '截取区域',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': '修改快捷键',
        'dialog.hotkey_prompt': '“{action}”的快捷键。\n例如：ctrl+alt+a',
        'notify.hotkey_set': '快捷键：{key}',
        'notify.hotkey_invalid': '快捷键无效：{key}',
        'notify.hotkey_conflict': '{key} 已被其他程序占用，可能无法生效',
        'notify.hotkey_failed': '无法绑定 {key}',
        'menu.cleanup': '删除旧截图',
        'menu.cleanup_never': '从不',
        'menu.cleanup_days': '超过 {days} 天',
        'notify.cleanup_on': '清理：超过 {days} 天（本次删除 {count} 个）',
        'notify.cleanup_off': '清理：已关闭',
    },
    'ja': {
        'lang.name': '日本語',
        'notify.no_clipboard_image': 'クリップボードに画像がありません',
        'notify.saved': '保存しました：{name}',
        'notify.quick_saved': 'クイック保存：{name}',
        'notify.area_saved': '範囲を保存：{name}',
        'notify.no_text': 'テキストが見つかりません',
        'notify.ocr_result': 'OCR（{count} 文字）：{preview}',
        'notify.ocr_error': 'OCR エラー：{error}',
        'notify.prefix_set': 'プレフィックス：{prefix}_…',
        'notify.prefix_cleared': 'プレフィックスをクリアしました',
        'notify.autoresize_on': '自動リサイズ：オン',
        'notify.autoresize_off': '自動リサイズ：オフ',
        'notify.autostart_on': '自動起動：オン',
        'notify.autostart_off': '自動起動：オフ',
        'notify.format_changed': '形式：{fmt}',
        'notify.log_empty': 'ログは空です — エラーはありません',
        'notify.language_changed': '言語：日本語',
        'msg.already_running': 'スクリーンショットヘルパーは既に実行中です — トレイアイコンを確認してください。',
        'dialog.save_title': 'スクリーンショットを名前を付けて保存...',
        'dialog.prefix_title': 'スクリーンショットのファイル名プレフィックス',
        'dialog.prefix_prompt': "ファイル名のプレフィックス（空 = デフォルト '{default}' を使用）：",
        'default.filename_base': 'スクリーンショット',
        'menu.title': 'スクリーンショットヘルパー',
        'menu.prefix_none': 'ファイル名プレフィックス：（なし）',
        'menu.prefix': 'ファイル名プレフィックス：{value}',
        'menu.autoresize': '大きい画像を自動リサイズ（>{px}px）',
        'menu.autostart': 'Windows と一緒に自動起動',
        'menu.format': '保存形式',
        'menu.open_folder': 'スクリーンショットフォルダを開く',
        'menu.open_log': 'エラーログを開く',
        'menu.language': '言語',
        'menu.restart': '再起動',
        'notify.restart_failed': '再起動できませんでした',
        'menu.exit': '終了',
        'menu.hotkeys': 'ショートカットキー',
        'action.dialog': 'ダイアログで保存',
        'action.quick': 'クイック保存',
        'action.area': '範囲をキャプチャ',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'ショートカットキーの変更',
        'dialog.hotkey_prompt': '「{action}」のショートカットキー。\n例: ctrl+alt+a',
        'notify.hotkey_set': 'ショートカットキー: {key}',
        'notify.hotkey_invalid': 'ショートカットキーが不正です: {key}',
        'notify.hotkey_conflict': '{key} は他のアプリが使用中です — 動作しない場合があります',
        'notify.hotkey_failed': '{key} を割り当てられませんでした',
        'menu.cleanup': '古いスクリーンショットを削除',
        'menu.cleanup_never': '削除しない',
        'menu.cleanup_days': '{days} 日より前',
        'notify.cleanup_on': 'クリーンアップ: {days} 日より前（今回 {count} 件削除）',
        'notify.cleanup_off': 'クリーンアップ: オフ',
    },
    'de': {
        'lang.name': 'Deutsch',
        'notify.no_clipboard_image': 'Zwischenablage enthält kein Bild',
        'notify.saved': 'Gespeichert: {name}',
        'notify.quick_saved': 'Schnell gespeichert: {name}',
        'notify.area_saved': 'Bereich gespeichert: {name}',
        'notify.no_text': 'Kein Text gefunden',
        'notify.ocr_result': 'OCR ({count} Zeichen): {preview}',
        'notify.ocr_error': 'OCR-Fehler: {error}',
        'notify.prefix_set': 'Präfix: {prefix}_…',
        'notify.prefix_cleared': 'Präfix zurückgesetzt',
        'notify.autoresize_on': 'Auto-Größenanpassung: an',
        'notify.autoresize_off': 'Auto-Größenanpassung: aus',
        'notify.autostart_on': 'Autostart: an',
        'notify.autostart_off': 'Autostart: aus',
        'notify.format_changed': 'Format: {fmt}',
        'notify.log_empty': 'Protokoll ist leer — noch keine Fehler',
        'notify.language_changed': 'Sprache: Deutsch',
        'msg.already_running': 'Screenshot-Helfer läuft bereits — siehe Taskleistensymbol.',
        'dialog.save_title': 'Screenshot speichern unter...',
        'dialog.prefix_title': 'Dateinamen-Präfix für Screenshots',
        'dialog.prefix_prompt': "Dateinamen-Präfix (leer = Standard '{default}' verwenden):",
        'default.filename_base': 'Screenshot',
        'menu.title': 'Screenshot-Helfer',
        'menu.prefix_none': 'Dateinamen-Präfix: (keins)',
        'menu.prefix': 'Dateinamen-Präfix: {value}',
        'menu.autoresize': 'Große automatisch verkleinern (>{px}px)',
        'menu.autostart': 'Mit Windows starten',
        'menu.format': 'Speicherformat',
        'menu.open_folder': 'Screenshot-Ordner öffnen',
        'menu.open_log': 'Fehlerprotokoll öffnen',
        'menu.language': 'Sprache',
        'menu.restart': 'Neu starten',
        'notify.restart_failed': 'Neustart fehlgeschlagen',
        'menu.exit': 'Beenden',
        'menu.hotkeys': 'Tastenkürzel',
        'action.dialog': 'Über Dialog speichern',
        'action.quick': 'Schnell speichern',
        'action.area': 'Bereich aufnehmen',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Tastenkürzel ändern',
        'dialog.hotkey_prompt': 'Tastenkürzel für „{action}“.\nZum Beispiel: ctrl+alt+a',
        'notify.hotkey_set': 'Tastenkürzel: {key}',
        'notify.hotkey_invalid': 'Kein gültiges Tastenkürzel: {key}',
        'notify.hotkey_conflict': '{key} ist bereits von einer anderen App belegt — funktioniert evtl. nicht',
        'notify.hotkey_failed': '{key} konnte nicht belegt werden',
        'menu.cleanup': 'Alte Screenshots löschen',
        'menu.cleanup_never': 'Nie',
        'menu.cleanup_days': 'Älter als {days} Tage',
        'notify.cleanup_on': 'Bereinigung: älter als {days} Tage (jetzt gelöscht: {count})',
        'notify.cleanup_off': 'Bereinigung: aus',
    },
    'it': {
        'lang.name': 'Italiano',
        'notify.no_clipboard_image': 'Nessuna immagine negli appunti',
        'notify.saved': 'Salvato: {name}',
        'notify.quick_saved': 'Salvataggio rapido: {name}',
        'notify.area_saved': 'Area salvata: {name}',
        'notify.no_text': 'Nessun testo trovato',
        'notify.ocr_result': 'OCR ({count} caratteri): {preview}',
        'notify.ocr_error': 'Errore OCR: {error}',
        'notify.prefix_set': 'Prefisso: {prefix}_…',
        'notify.prefix_cleared': 'Prefisso azzerato',
        'notify.autoresize_on': 'Ridimensionamento automatico: attivo',
        'notify.autoresize_off': 'Ridimensionamento automatico: disattivato',
        'notify.autostart_on': 'Avvio automatico: attivo',
        'notify.autostart_off': 'Avvio automatico: disattivato',
        'notify.format_changed': 'Formato: {fmt}',
        'notify.log_empty': 'Registro vuoto — nessun errore',
        'notify.language_changed': 'Lingua: Italiano',
        'msg.already_running': "Screenshot helper è già in esecuzione — controlla l'icona nella barra delle applicazioni.",
        'dialog.save_title': 'Salva screenshot come...',
        'dialog.prefix_title': 'Prefisso del nome file dello screenshot',
        'dialog.prefix_prompt': "Prefisso del nome file (vuoto = usa predefinito '{default}'):",
        'default.filename_base': 'Screenshot',
        'menu.title': 'Screenshot Helper',
        'menu.prefix_none': 'Prefisso nome file: (nessuno)',
        'menu.prefix': 'Prefisso nome file: {value}',
        'menu.autoresize': 'Ridimensiona immagini grandi (>{px}px)',
        'menu.autostart': 'Avvia con Windows',
        'menu.format': 'Formato di salvataggio',
        'menu.open_folder': 'Apri cartella screenshot',
        'menu.open_log': 'Apri registro errori',
        'menu.language': 'Lingua',
        'menu.restart': 'Riavvia',
        'notify.restart_failed': 'Impossibile riavviare',
        'menu.exit': 'Esci',
        'menu.hotkeys': 'Scorciatoie',
        'action.dialog': 'Salva tramite finestra',
        'action.quick': 'Salvataggio rapido',
        'action.area': 'Cattura area',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Cambia scorciatoia',
        'dialog.hotkey_prompt': 'Scorciatoia per "{action}".\nAd esempio: ctrl+alt+a',
        'notify.hotkey_set': 'Scorciatoia: {key}',
        'notify.hotkey_invalid': 'Scorciatoia non valida: {key}',
        'notify.hotkey_conflict': '{key} è già usata da un\'altra app — potrebbe non funzionare',
        'notify.hotkey_failed': 'Impossibile assegnare {key}',
        'menu.cleanup': 'Elimina vecchi screenshot',
        'menu.cleanup_never': 'Mai',
        'menu.cleanup_days': 'Più vecchi di {days} giorni',
        'notify.cleanup_on': 'Pulizia: più vecchi di {days} giorni (eliminati ora: {count})',
        'notify.cleanup_off': 'Pulizia: disattivata',
    },
    'es': {
        'lang.name': 'Español',
        'notify.no_clipboard_image': 'El portapapeles no tiene imagen',
        'notify.saved': 'Guardado: {name}',
        'notify.quick_saved': 'Guardado rápido: {name}',
        'notify.area_saved': 'Área guardada: {name}',
        'notify.no_text': 'No se encontró texto',
        'notify.ocr_result': 'OCR ({count} caracteres): {preview}',
        'notify.ocr_error': 'Error de OCR: {error}',
        'notify.prefix_set': 'Prefijo: {prefix}_…',
        'notify.prefix_cleared': 'Prefijo borrado',
        'notify.autoresize_on': 'Autoajuste: activado',
        'notify.autoresize_off': 'Autoajuste: desactivado',
        'notify.autostart_on': 'Inicio automático: activado',
        'notify.autostart_off': 'Inicio automático: desactivado',
        'notify.format_changed': 'Formato: {fmt}',
        'notify.log_empty': 'Registro vacío — aún no hay errores',
        'notify.language_changed': 'Idioma: Español',
        'msg.already_running': 'El asistente de capturas ya está en ejecución — revisa el icono de la bandeja.',
        'dialog.save_title': 'Guardar captura como...',
        'dialog.prefix_title': 'Prefijo del nombre de archivo',
        'dialog.prefix_prompt': "Prefijo del nombre (vacío = usar predeterminado '{default}'):",
        'default.filename_base': 'Captura',
        'menu.title': 'Asistente de capturas',
        'menu.prefix_none': 'Prefijo del nombre: (ninguno)',
        'menu.prefix': 'Prefijo del nombre: {value}',
        'menu.autoresize': 'Reducir imágenes grandes (>{px}px)',
        'menu.autostart': 'Iniciar con Windows',
        'menu.format': 'Formato de guardado',
        'menu.open_folder': 'Abrir carpeta de capturas',
        'menu.open_log': 'Abrir registro de errores',
        'menu.language': 'Idioma',
        'menu.restart': 'Reiniciar',
        'notify.restart_failed': 'No se pudo reiniciar',
        'menu.exit': 'Salir',
        'menu.hotkeys': 'Atajos de teclado',
        'action.dialog': 'Guardar con diálogo',
        'action.quick': 'Guardado rápido',
        'action.area': 'Capturar área',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Cambiar atajo',
        'dialog.hotkey_prompt': 'Atajo para «{action}».\nPor ejemplo: ctrl+alt+a',
        'notify.hotkey_set': 'Atajo: {key}',
        'notify.hotkey_invalid': 'Atajo no válido: {key}',
        'notify.hotkey_conflict': '{key} ya lo usa otra aplicación — puede que no funcione',
        'notify.hotkey_failed': 'No se pudo asignar {key}',
        'menu.cleanup': 'Eliminar capturas antiguas',
        'menu.cleanup_never': 'Nunca',
        'menu.cleanup_days': 'Más de {days} días',
        'notify.cleanup_on': 'Limpieza: más de {days} días (eliminadas ahora: {count})',
        'notify.cleanup_off': 'Limpieza: desactivada',
    },
    'fr': {
        'lang.name': 'Français',
        'notify.no_clipboard_image': "Le presse-papiers ne contient pas d'image",
        'notify.saved': 'Enregistré : {name}',
        'notify.quick_saved': 'Enregistrement rapide : {name}',
        'notify.area_saved': 'Zone enregistrée : {name}',
        'notify.no_text': 'Aucun texte trouvé',
        'notify.ocr_result': 'OCR ({count} caractères) : {preview}',
        'notify.ocr_error': 'Erreur OCR : {error}',
        'notify.prefix_set': 'Préfixe : {prefix}_…',
        'notify.prefix_cleared': 'Préfixe réinitialisé',
        'notify.autoresize_on': 'Redimensionnement auto : activé',
        'notify.autoresize_off': 'Redimensionnement auto : désactivé',
        'notify.autostart_on': 'Démarrage auto : activé',
        'notify.autostart_off': 'Démarrage auto : désactivé',
        'notify.format_changed': 'Format : {fmt}',
        'notify.log_empty': "Journal vide — aucune erreur pour l'instant",
        'notify.language_changed': 'Langue : Français',
        'msg.already_running': "L'assistant de capture est déjà lancé — voir l'icône dans la barre d'état système.",
        'dialog.save_title': 'Enregistrer la capture sous...',
        'dialog.prefix_title': 'Préfixe du nom de fichier',
        'dialog.prefix_prompt': "Préfixe du nom de fichier (vide = utiliser '{default}' par défaut) :",
        'default.filename_base': 'Capture',
        'menu.title': 'Assistant de capture',
        'menu.prefix_none': 'Préfixe du nom : (aucun)',
        'menu.prefix': 'Préfixe du nom : {value}',
        'menu.autoresize': 'Réduire les grandes images (>{px}px)',
        'menu.autostart': 'Démarrer avec Windows',
        'menu.format': "Format d'enregistrement",
        'menu.open_folder': 'Ouvrir le dossier des captures',
        'menu.open_log': 'Ouvrir le journal des erreurs',
        'menu.language': 'Langue',
        'menu.restart': 'Redémarrer',
        'notify.restart_failed': 'Échec du redémarrage',
        'menu.exit': 'Quitter',
        'menu.hotkeys': 'Raccourcis clavier',
        'action.dialog': 'Enregistrer via la boîte de dialogue',
        'action.quick': 'Enregistrement rapide',
        'action.area': 'Capturer une zone',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Modifier le raccourci',
        'dialog.hotkey_prompt': 'Raccourci pour « {action} ».\nPar exemple : ctrl+alt+a',
        'notify.hotkey_set': 'Raccourci : {key}',
        'notify.hotkey_invalid': 'Raccourci invalide : {key}',
        'notify.hotkey_conflict': '{key} est déjà utilisé par une autre application — il risque de ne pas fonctionner',
        'notify.hotkey_failed': 'Impossible d\'attribuer {key}',
        'menu.cleanup': 'Supprimer les anciennes captures',
        'menu.cleanup_never': 'Jamais',
        'menu.cleanup_days': 'Plus de {days} jours',
        'notify.cleanup_on': 'Nettoyage : plus de {days} jours (supprimées : {count})',
        'notify.cleanup_off': 'Nettoyage : désactivé',
    },
    'pt': {
        'lang.name': 'Português',
        'notify.no_clipboard_image': 'A área de transferência não tem imagem',
        'notify.saved': 'Salvo: {name}',
        'notify.quick_saved': 'Salvo rapidamente: {name}',
        'notify.area_saved': 'Área salva: {name}',
        'notify.no_text': 'Nenhum texto encontrado',
        'notify.ocr_result': 'OCR ({count} caracteres): {preview}',
        'notify.ocr_error': 'Erro de OCR: {error}',
        'notify.prefix_set': 'Prefixo: {prefix}_…',
        'notify.prefix_cleared': 'Prefixo limpo',
        'notify.autoresize_on': 'Redimensionamento automático: ligado',
        'notify.autoresize_off': 'Redimensionamento automático: desligado',
        'notify.autostart_on': 'Inicialização automática: ligada',
        'notify.autostart_off': 'Inicialização automática: desligada',
        'notify.format_changed': 'Formato: {fmt}',
        'notify.log_empty': 'Registro vazio — ainda sem erros',
        'notify.language_changed': 'Idioma: Português',
        'msg.already_running': 'O assistente de capturas já está em execução — veja o ícone na bandeja.',
        'dialog.save_title': 'Salvar captura como...',
        'dialog.prefix_title': 'Prefixo do nome do arquivo',
        'dialog.prefix_prompt': "Prefixo do nome (vazio = usar padrão '{default}'):",
        'default.filename_base': 'Captura',
        'menu.title': 'Assistente de capturas',
        'menu.prefix_none': 'Prefixo do nome: (nenhum)',
        'menu.prefix': 'Prefixo do nome: {value}',
        'menu.autoresize': 'Redimensionar imagens grandes (>{px}px)',
        'menu.autostart': 'Iniciar com o Windows',
        'menu.format': 'Formato de salvamento',
        'menu.open_folder': 'Abrir pasta de capturas',
        'menu.open_log': 'Abrir registro de erros',
        'menu.language': 'Idioma',
        'menu.restart': 'Reiniciar',
        'notify.restart_failed': 'Não foi possível reiniciar',
        'menu.exit': 'Sair',
        'menu.hotkeys': 'Atalhos de teclado',
        'action.dialog': 'Salvar via caixa de diálogo',
        'action.quick': 'Salvamento rápido',
        'action.area': 'Capturar área',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': 'Alterar atalho',
        'dialog.hotkey_prompt': 'Atalho para "{action}".\nPor exemplo: ctrl+alt+a',
        'notify.hotkey_set': 'Atalho: {key}',
        'notify.hotkey_invalid': 'Atalho inválido: {key}',
        'notify.hotkey_conflict': '{key} já está em uso por outro aplicativo — pode não funcionar',
        'notify.hotkey_failed': 'Não foi possível atribuir {key}',
        'menu.cleanup': 'Excluir capturas antigas',
        'menu.cleanup_never': 'Nunca',
        'menu.cleanup_days': 'Mais de {days} dias',
        'notify.cleanup_on': 'Limpeza: mais de {days} dias (excluídas agora: {count})',
        'notify.cleanup_off': 'Limpeza: desativada',
    },
    'ko': {
        'lang.name': '한국어',
        'notify.no_clipboard_image': '클립보드에 이미지가 없습니다',
        'notify.saved': '저장됨: {name}',
        'notify.quick_saved': '빠른 저장: {name}',
        'notify.area_saved': '영역 저장됨: {name}',
        'notify.no_text': '텍스트를 찾을 수 없습니다',
        'notify.ocr_result': 'OCR ({count}자): {preview}',
        'notify.ocr_error': 'OCR 오류: {error}',
        'notify.prefix_set': '접두사: {prefix}_…',
        'notify.prefix_cleared': '접두사 초기화됨',
        'notify.autoresize_on': '자동 크기 조정: 켜짐',
        'notify.autoresize_off': '자동 크기 조정: 꺼짐',
        'notify.autostart_on': '자동 시작: 켜짐',
        'notify.autostart_off': '자동 시작: 꺼짐',
        'notify.format_changed': '형식: {fmt}',
        'notify.log_empty': '로그가 비어 있음 — 아직 오류 없음',
        'notify.language_changed': '언어: 한국어',
        'msg.already_running': '스크린샷 도우미가 이미 실행 중입니다 — 트레이 아이콘을 확인하세요.',
        'dialog.save_title': '스크린샷 다른 이름으로 저장...',
        'dialog.prefix_title': '스크린샷 파일 이름 접두사',
        'dialog.prefix_prompt': "파일 이름 접두사 (비움 = 기본값 '{default}' 사용):",
        'default.filename_base': '스크린샷',
        'menu.title': '스크린샷 도우미',
        'menu.prefix_none': '파일 이름 접두사: (없음)',
        'menu.prefix': '파일 이름 접두사: {value}',
        'menu.autoresize': '큰 이미지 자동 축소 (>{px}px)',
        'menu.autostart': 'Windows와 함께 시작',
        'menu.format': '저장 형식',
        'menu.open_folder': '스크린샷 폴더 열기',
        'menu.open_log': '오류 로그 열기',
        'menu.language': '언어',
        'menu.restart': '다시 시작',
        'notify.restart_failed': '다시 시작할 수 없습니다',
        'menu.exit': '종료',
        'menu.hotkeys': '단축키',
        'action.dialog': '대화 상자로 저장',
        'action.quick': '빠른 저장',
        'action.area': '영역 캡처',
        'action.ocr': 'OCR',
        'dialog.hotkey_title': '단축키 변경',
        'dialog.hotkey_prompt': '"{action}"의 단축키.\n예: ctrl+alt+a',
        'notify.hotkey_set': '단축키: {key}',
        'notify.hotkey_invalid': '올바른 단축키가 아닙니다: {key}',
        'notify.hotkey_conflict': '{key} 은(는) 다른 앱이 사용 중입니다 — 작동하지 않을 수 있습니다',
        'notify.hotkey_failed': '{key} 을(를) 지정할 수 없습니다',
        'menu.cleanup': '오래된 스크린샷 삭제',
        'menu.cleanup_never': '삭제 안 함',
        'menu.cleanup_days': '{days}일 이전',
        'notify.cleanup_on': '정리: {days}일 이전 (지금 삭제: {count}개)',
        'notify.cleanup_off': '정리: 꺼짐',
    },
}

MAX_DIMENSION = 1920  # auto-resize: longest side won't exceed this
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "ScreenshotToTerminal"

DEFAULT_FORMAT = 'png'  # default save format (png / jpeg)


# ============================================================
# Глобальное состояние
# ============================================================
stop_event = threading.Event()
action_queue: "queue.Queue[str]" = queue.Queue()
icon_ref = None
_mutex_handle = None
_config_cache = None
_heartbeat_seen = threading.Event()


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


def get_format() -> str:
    fmt = get_config("image_format", DEFAULT_FORMAT)
    return fmt if fmt in ('png', 'jpeg') else DEFAULT_FORMAT


def _default_extension() -> str:
    return '.png' if get_format() == 'png' else '.jpeg'


# ============================================================
# Горячие клавиши: хранение, отображение, проверка занятости
# ============================================================
def get_hotkey(action: str) -> str:
    stored = (get_config("hotkeys", {}) or {}).get(action)
    if isinstance(stored, str) and stored.strip():
        return stored.strip().lower()
    return HOTKEY_DEFAULTS[action]


def set_hotkey(action: str, combo: str) -> None:
    hotkeys = dict(get_config("hotkeys", {}) or {})
    hotkeys[action] = combo
    set_config("hotkeys", hotkeys)


def _pretty_hotkey(combo: str) -> str:
    return '+'.join(part.strip().title() for part in combo.split('+'))


_MOD_FLAGS = {'alt': 0x0001, 'ctrl': 0x0002, 'control': 0x0002,
              'shift': 0x0004, 'win': 0x0008, 'windows': 0x0008}


def _combo_to_win_hotkey(combo: str):
    """'ctrl+alt+a' -> (модификаторы, virtual key) в терминах RegisterHotKey."""
    mods, vk = 0, None
    for part in combo.lower().split('+'):
        part = part.strip()
        if part in _MOD_FLAGS:
            mods |= _MOD_FLAGS[part]
        elif len(part) == 1:
            char = part.upper()
            if 'A' <= char <= 'Z' or '0' <= char <= '9':
                # У латиницы и цифр virtual key совпадает с ASCII и не зависит
                # от раскладки. Через VkKeyScanW они бы отваливались, когда
                # активна русская раскладка: латинской «a» в ней просто нет.
                vk = ord(char)
            else:
                # c_wchar обязателен: без него ctypes передаёт указатель на
                # строку, а VkKeyScanW ждёт сам символ.
                scan = ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(part))
                if scan == -1:
                    return None
                vk = scan & 0xFF
        elif part.startswith('f') and part[1:].isdigit():
            vk = 0x70 + int(part[1:]) - 1  # F1..F24
        else:
            return None  # экзотическая клавиша — проверить не сможем
    if vk is None or not mods:
        return None
    return mods, vk


def is_hotkey_taken(combo: str) -> bool:
    """True, если комбинацию уже держит другое приложение.

    Видны только те, кто регистрируется штатным RegisterHotKey — а это
    большинство программ. Утилиты на low-level хуке (как эта) так не
    определяются: они перехватывают клавиши раньше и молча.
    """
    parsed = _combo_to_win_hotkey(combo)
    if not parsed:
        return False
    mods, vk = parsed
    user32 = ctypes.windll.user32
    hotkey_id = 0xB00B
    if user32.RegisterHotKey(None, hotkey_id, mods, vk):
        user32.UnregisterHotKey(None, hotkey_id)
        return False
    return True


# ============================================================
# Локализация
# ============================================================
def get_language() -> str:
    lang = get_config("language", DEFAULT_LANGUAGE)
    if isinstance(lang, str) and lang in I18N:
        return lang
    return DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    if code in I18N:
        set_config("language", code)


def t(key: str, **kwargs) -> str:
    table = I18N.get(get_language()) or I18N[DEFAULT_LANGUAGE]
    template = table.get(key) or I18N[DEFAULT_LANGUAGE].get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


# ============================================================
# Утилиты
# ============================================================
def _write_log(level: str, msg: str) -> None:
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        try:
            if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
                os.replace(LOG_FILE, LOG_FILE + ".1")
        except OSError:
            pass  # файла ещё нет либо он занят — не повод терять запись
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n")
    except Exception:
        pass


def log_error(msg: str) -> None:
    _write_log("ERROR", msg)


def log_info(msg: str) -> None:
    _write_log("INFO", msg)


def log_debug(msg: str) -> None:
    """Подробности вроде сырых результатов OCR — только когда их включили.

    Иначе каждый Ctrl+Alt+D писал в error.log две строки распознанного текста,
    и «лог ошибок» превращался в историю буфера обмена.
    """
    if get_config("debug_log", False):
        _write_log("DEBUG", msg)


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


def _generate_filename(extension: str = None) -> str:
    if extension is None:
        extension = _default_extension()
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    prefix = _sanitize_prefix(get_config("filename_prefix", "") or "")
    base = prefix if prefix else t('default.filename_base')
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
        notify(t('notify.no_clipboard_image'))
        return

    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return

        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        last_dir = load_last_dir()
        if not os.path.isdir(last_dir):
            last_dir = DEFAULT_SCREENSHOTS_DIR

        initial_filename = _generate_filename()

        # Тип файла в диалоге: выбранный формат идёт первым (по умолчанию)
        png_ft = ("PNG Image", "*.png")
        jpeg_ft = ("JPEG Image", "*.jpeg")
        ordered = [png_ft, jpeg_ft] if get_format() == 'png' else [jpeg_ft, png_ft]
        filetypes = ordered + [("All files", "*.*")]

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        try:
            filepath = filedialog.asksaveasfilename(
                title=t('dialog.save_title'),
                initialdir=last_dir,
                initialfile=initial_filename,
                defaultextension=_default_extension(),
                filetypes=filetypes,
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
        notify(t('notify.saved', name=os.path.basename(filepath)))
    except Exception as e:
        log_error(f"save_screenshot_with_dialog: {e}")


def save_screenshot_quick() -> None:
    if not clipboard_has_image():
        notify(t('notify.no_clipboard_image'))
        return

    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return

        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
        filename = _generate_filename()
        filepath = os.path.join(DEFAULT_SCREENSHOTS_DIR, filename)

        saved = _save_image(image, filepath)
        set_clipboard_image_and_text(saved, filepath)
        notify(t('notify.quick_saved', name=filename))
    except Exception as e:
        log_error(f"save_screenshot_quick: {e}")


# ============================================================
# Захват области экрана через overlay
# ============================================================
def _capture_screen_area_bbox():
    """Spotlight-overlay: затемняем экран, область под курсором — без затемнения. Возвращает (x1, y1, x2, y2) или None.

    Производительность: затемнённый скриншот рисуется фоном ОДИН раз, а область
    выделения делается прозрачной через -transparentcolor (там виден живой экран
    на полной яркости). Прозрачный прямоугольник двигается через canvas.coords()
    по сплошной заливке — без stipple и без PIL-операций на кадр — поэтому плавно
    даже на 4K. Обновления коалесцируются до ~60fps.
    """
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

    # Magic-цвет для прозрачной «дырки». enhance(0.5) не даёт каналам значение
    # 255, поэтому #ff00ff гарантированно отсутствует в затемнённом фоне.
    MAGIC = '#ff00ff'

    root = tk.Tk()
    root.attributes('-topmost', True)
    root.overrideredirect(True)
    root.geometry(f"{virtual_w}x{virtual_h}+{virtual_x}+{virtual_y}")
    root.configure(cursor='crosshair')
    try:
        root.attributes('-transparentcolor', MAGIC)
    except Exception:
        pass

    canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0, bg='black',
                       width=virtual_w, height=virtual_h)
    canvas.pack(fill='both', expand=True)

    # Фон — затемнённый скриншот целиком, конвертируется в PhotoImage один раз
    dim_tk = ImageTk.PhotoImage(dim)
    canvas.create_image(0, 0, anchor='nw', image=dim_tk)
    canvas._dim_ref = dim_tk  # держим ссылку, иначе сборщик уберёт

    # «Дырка» (прозрачная область) + красная рамка поверх неё
    hole = canvas.create_rectangle(0, 0, 0, 0, fill=MAGIC, outline='', width=0)
    sel_rect = canvas.create_rectangle(0, 0, 0, 0, outline='red', width=2)

    # Подпись с размером выделения. Рисуется по затемнённому фону (не по «дырке»),
    # иначе попала бы в кадр — поэтому держим её снаружи рамки.
    size_bg = canvas.create_rectangle(0, 0, 0, 0, fill='#1a1a1a', outline='', state='hidden')
    size_text = canvas.create_text(0, 0, text='', anchor='nw', fill='white',
                                   font=('Segoe UI', 11, 'bold'), state='hidden')

    state = {'start': None, 'bbox': None, 'after_id': None, 'last': None}

    def _place_size_label(cx1, cy1, cx2, cy2):
        width, height = int(cx2 - cx1), int(cy2 - cy1)
        if width <= 0 or height <= 0:
            canvas.itemconfig(size_text, state='hidden')
            canvas.itemconfig(size_bg, state='hidden')
            return
        # Под рамкой, а если там край экрана — над ней
        label_y = cy2 + 8 if cy2 + 34 < virtual_h else max(0, cy1 - 28)
        label_x = min(cx1 + 2, max(0, virtual_w - 96))
        canvas.coords(size_text, label_x, label_y)
        canvas.itemconfig(size_text, text=f"{width} × {height}", state='normal')
        bounds = canvas.bbox(size_text)
        if bounds:
            canvas.coords(size_bg, bounds[0] - 6, bounds[1] - 4,
                          bounds[2] + 6, bounds[3] + 4)
            canvas.itemconfig(size_bg, state='normal')
        canvas.tag_raise(size_bg)
        canvas.tag_raise(size_text)

    def set_selection(cx1, cy1, cx2, cy2):
        cx1, cx2 = sorted((cx1, cx2))
        cy1, cy2 = sorted((cy1, cy2))
        cx1 = max(0, min(virtual_w, cx1))
        cy1 = max(0, min(virtual_h, cy1))
        cx2 = max(0, min(virtual_w, cx2))
        cy2 = max(0, min(virtual_h, cy2))
        canvas.coords(hole, cx1, cy1, cx2, cy2)
        canvas.coords(sel_rect, cx1, cy1, cx2, cy2)
        _place_size_label(cx1, cy1, cx2, cy2)

    def _apply_pending():
        state['after_id'] = None
        if state['last'] is not None:
            set_selection(*state['last'])

    def finish(bbox):
        state['bbox'] = bbox
        if state['after_id'] is not None:
            try:
                canvas.after_cancel(state['after_id'])
            except Exception:
                pass
            state['after_id'] = None
        try:
            root.grab_release()
        except Exception:
            pass
        try:
            root.quit()  # завершает mainloop; destroy — после него
        except Exception:
            pass

    def on_press(event):
        state['start'] = (event.x_root, event.y_root)

    def on_drag(event):
        if not state['start']:
            return
        sx, sy = state['start']
        # Запоминаем последнюю позицию; применяем не чаще ~60fps (коалесцируем)
        state['last'] = (sx - virtual_x, sy - virtual_y,
                         event.x_root - virtual_x, event.y_root - virtual_y)
        if state['after_id'] is None:
            state['after_id'] = canvas.after(16, _apply_pending)

    def on_release(event):
        if state['start']:
            x1 = min(state['start'][0], event.x_root)
            y1 = min(state['start'][1], event.y_root)
            x2 = max(state['start'][0], event.x_root)
            y2 = max(state['start'][1], event.y_root)
            if (x2 - x1) > 5 and (y2 - y1) > 5:
                finish((x1, y1, x2, y2))
                return
        finish(None)

    def on_cancel(event=None):
        finish(None)

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    canvas.bind('<ButtonPress-3>', on_cancel)  # правый клик — отмена
    root.bind('<Escape>', on_cancel)
    root.protocol('WM_DELETE_WINDOW', on_cancel)

    # Фокус и захват ввода — чтобы Escape гарантированно срабатывал и mainloop
    # всегда мог завершиться (иначе worker-поток мог зависнуть навсегда).
    try:
        root.update_idletasks()  # окно должно быть отображено до focus/grab
    except Exception:
        pass
    try:
        root.focus_force()
        canvas.focus_set()
    except Exception:
        pass
    try:
        root.grab_set()
    except Exception:
        pass

    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass
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
        filename = _generate_filename()
        filepath = os.path.join(DEFAULT_SCREENSHOTS_DIR, filename)

        saved = _save_image(image, filepath)
        set_clipboard_image_and_text(saved, filepath)
        notify(t('notify.area_saved', name=filename))
    except Exception as e:
        log_error(f"save_screenshot_area: {e}")


# ============================================================
# OCR через Windows.Media.Ocr (без интернета)
# ============================================================
# Диапазоны письменностей: по ним отличаем осмысленный результат от того,
# что чужой движок вычитал «на свой лад» (`nepe3anyu.1e1-l` вместо «перезапустил»).
_SCRIPT_RANGES = {
    'cyrillic': ((0x0400, 0x04FF),),
    'latin': ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F)),
    'cjk': ((0x3400, 0x4DBF), (0x4E00, 0x9FFF)),
    'kana': ((0x3040, 0x30FF),),
    'hangul': ((0x1100, 0x11FF), (0xAC00, 0xD7AF)),
}

# Какую письменность ждём от движка конкретного языка
_LANG_SCRIPTS = {
    'ru': ('cyrillic',), 'uk': ('cyrillic',), 'be': ('cyrillic',),
    'bg': ('cyrillic',), 'sr': ('cyrillic',), 'mk': ('cyrillic',),
    'zh': ('cjk',), 'ja': ('kana', 'cjk'), 'ko': ('hangul',),
}
_DEFAULT_SCRIPTS = ('latin',)


def _scripts_of_lang(tag: str) -> tuple:
    return _LANG_SCRIPTS.get((tag or '').split('-')[0].lower(), _DEFAULT_SCRIPTS)


def _in_scripts(ch: str, scripts: tuple) -> bool:
    code = ord(ch)
    for name in scripts:
        for low, high in _SCRIPT_RANGES[name]:
            if low <= code <= high:
                return True
    return False


def _score_ocr_text(text: str, scripts: tuple) -> int:
    """Насколько текст похож на осмысленный для этой письменности.

    Одного подсчёта «своих» букв мало: кириллица и латиница похожи начертанием,
    поэтому английский движок читает «Перезапусти сервер» как «nepeaanycTL4
    cepBep» — формально это тоже латинские слова. Отличает их рваность:
    цифры вместо букв и заглавные посреди слова. За них и штрафуем.
    """
    score = 0
    for chunk in text.split():
        letters = sum(1 for c in chunk if _in_scripts(c, scripts))
        if letters < 2 or letters < len(chunk) * 0.6:
            continue
        word_score = letters
        if any(c.isdigit() for c in chunk):
            word_score -= 3
        word_score -= sum(1 for c in chunk[1:] if c.isupper()) * 2
        score += max(0, word_score)
    return score


def _ocr_languages() -> list:
    """Какими движками пробовать: язык интерфейса, затем английский, затем
    остальные установленные в системе."""
    override = get_config("ocr_languages", None)
    try:
        # ВНИМАНИЕ: не переписывать на `for lang in languages` — итератор этой
        # WinRT-коллекции роняет процесс с access violation (проверено на
        # winsdk 1.0.0b10 / Python 3.13, воспроизводится стабильно). Access
        # violation не перехватывается try/except, приложение умирает молча.
        # Обращение по индексу работает надёжно.
        languages = OcrEngine.available_recognizer_languages
        available = [languages[i].language_tag for i in range(len(languages))]
    except Exception as e:
        log_error(f"ocr languages: {e}")
        available = list(OCR_LANGUAGES)

    if isinstance(override, list) and override:
        ordered = [tag for tag in override if tag in available] or available
    else:
        ui = get_language().lower()
        ordered = [tag for tag in available if tag.lower().split('-')[0] == ui]
        ordered += [tag for tag in available
                    if tag.lower().startswith('en') and tag not in ordered]
        ordered += [tag for tag in available if tag not in ordered]
    return ordered[:MAX_OCR_ENGINES]


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

    results = []
    for tag in _ocr_languages():
        try:
            lang = Language(tag)
            if not OcrEngine.is_language_supported(lang):
                continue
            engine = OcrEngine.try_create_from_language(lang)
            if engine is None:
                continue
            result = await engine.recognize_async(bitmap)
            text = (result.text or "").strip()
            if not text:
                continue
            score = _score_ocr_text(text, _scripts_of_lang(tag))
            results.append((score, text))
            preview = text[:80].replace('\n', ' ')
            log_debug(f"ocr[{tag}] score={score} len={len(text)} | {preview}")
        except Exception as e:
            log_error(f"ocr engine {tag}: {e}")

    if not results:
        return ""
    # Побеждает движок, чей результат больше похож на текст его языка.
    # Сортировка стабильна, поэтому при равном счёте выигрывает тот, кто шёл
    # раньше в _ocr_languages() — то есть язык интерфейса.
    results.sort(key=lambda item: item[0], reverse=True)
    return results[0][1]


def ocr_pil_image(pil_image: Image.Image) -> str:
    return asyncio.run(_ocr_pil_image_async(pil_image))


def ocr_from_clipboard() -> None:
    if not clipboard_has_image():
        notify(t('notify.no_clipboard_image'))
        return
    try:
        image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            return
        text = ocr_pil_image(image)
        if not text:
            notify(t('notify.no_text'))
            return
        set_clipboard_text(text)
        preview = text[:60].replace('\n', ' ').replace('\r', ' ')
        if len(text) > 60:
            preview += '…'
        notify(t('notify.ocr_result', count=len(text), preview=preview))
    except Exception as e:
        log_error(f"ocr_from_clipboard: {e}")
        notify(t('notify.ocr_error', error=e))


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
            t('dialog.prefix_title'),
            t('dialog.prefix_prompt', default=t('default.filename_base')),
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
        notify(t('notify.prefix_set', prefix=cleaned))
    else:
        notify(t('notify.prefix_cleared'))


# ============================================================
# Диалог смены горячей клавиши
# ============================================================
def show_hotkey_dialog(action: str) -> None:
    if action not in HOTKEY_DEFAULTS:
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        new_value = simpledialog.askstring(
            t('dialog.hotkey_title'),
            t('dialog.hotkey_prompt', action=t('action.' + action)),
            initialvalue=get_hotkey(action),
            parent=root,
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if new_value is None:
        return  # «Отмена»

    combo = new_value.strip().lower()
    if not combo:
        return

    try:
        keyboard.parse_hotkey(combo)
    except Exception:
        notify(t('notify.hotkey_invalid', key=new_value.strip()))
        return

    # Занятую комбинацию всё равно ставим: low-level хук перехватит клавиши
    # раньше владельца — но предупредить стоит, поведение будет неочевидным.
    if combo != get_hotkey(action) and is_hotkey_taken(combo):
        notify(t('notify.hotkey_conflict', key=_pretty_hotkey(combo)))

    set_hotkey(action, combo)
    register_hotkeys()
    notify(t('notify.hotkey_set', key=_pretty_hotkey(combo)))
    if icon_ref is not None:
        try:
            icon_ref.update_menu()
        except Exception:
            pass


# ============================================================
# Автоудаление старых снимков
# ============================================================
def cleanup_old_screenshots() -> int:
    """Удаляет снимки старше настроенного срока. Возвращает число удалённых."""
    days = get_config("cleanup_days", 0)
    if not isinstance(days, int) or days <= 0:
        return 0

    cutoff = time.time() - days * 86400
    removed = 0
    try:
        for name in os.listdir(DEFAULT_SCREENSHOTS_DIR):
            # Чужие файлы в папке (в т.ч. снимки самой Windows) не трогаем —
            # только то, что назвала эта программа.
            if not SCREENSHOT_NAME_RE.match(name):
                continue
            path = os.path.join(DEFAULT_SCREENSHOTS_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError as e:
                log_error(f"cleanup {name}: {e}")
    except FileNotFoundError:
        return 0
    except Exception as e:
        log_error(f"cleanup: {e}")
        return 0

    if removed:
        log_info(f"cleanup: удалено {removed} файлов старше {days} дн.")
    return removed


def cleanup_loop() -> None:
    delay = 60  # первый прогон — через минуту после старта, не в момент запуска
    while not stop_event.wait(delay):
        delay = CLEANUP_INTERVAL
        try:
            cleanup_old_screenshots()
        except Exception as e:
            log_error(f"cleanup_loop: {e}")


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


_HOTKEY_CALLBACKS = {
    'dialog': on_hotkey_dialog,
    'quick': on_hotkey_quick,
    'area': on_hotkey_area,
    'ocr': on_hotkey_ocr,
}


def register_hotkeys() -> None:
    """Перевешивает все хоткеи по текущим настройкам."""
    try:
        keyboard.remove_all_hotkeys()
    except Exception:
        pass
    for action, callback in _HOTKEY_CALLBACKS.items():
        combo = get_hotkey(action)
        try:
            keyboard.add_hotkey(combo, callback)
        except Exception as e:
            log_error(f"add_hotkey {action}={combo}: {e}")
            notify(t('notify.hotkey_failed', key=_pretty_hotkey(combo)))

    # Служебный хоткей самопроверки — регистрируется тем же способом, что и
    # рабочие, поэтому отваливается вместе с ними и годится как индикатор.
    try:
        keyboard.add_hotkey(HEARTBEAT_SCAN, _on_heartbeat)
    except Exception as e:
        log_error(f"add_hotkey heartbeat: {e}")


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
        elif action.startswith('set_hotkey:'):
            show_hotkey_dialog(action.split(':', 1)[1])


# ============================================================
# Watchdog состояния клавиатуры
# ============================================================
# keyboard ищет хоткей по ТОЧНОМУ набору зажатых клавиш:
#   hotkey = tuple(sorted(_pressed_events)); self.nonblocking_hotkeys[hotkey]
# Набор ведётся только по событиям low-level хука. Если KEY_UP до хука не дошёл
# (клавишу отпустили, когда фокус был в окне админ-процесса, на UAC-промпте,
# экране блокировки или в полноэкранной игре), клавиша остаётся в наборе
# навсегда — и ВСЕ хоткеи молча перестают срабатывать до перезапуска процесса.
# Раз в WATCHDOG_INTERVAL сверяем набор с физическим состоянием клавиш
# и выкидываем фантомы.
WATCHDOG_INTERVAL = 2.0
MAPVK_VSC_TO_VK_EX = 3
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
_SIDED_VK = {0xA0: VK_SHIFT, 0xA1: VK_SHIFT,      # left/right shift
             0xA2: VK_CONTROL, 0xA3: VK_CONTROL,  # left/right ctrl
             0xA4: VK_MENU, 0xA5: VK_MENU}        # left/right alt


def _is_physically_pressed(scan_code: int) -> bool:
    """True, если клавиша реально удерживается прямо сейчас."""
    user32 = ctypes.windll.user32
    # keyboard хранит scan_code как `scan_code or -vk` — отрицательное значение
    # означает, что скан-кода не было и это сразу virtual key.
    vk = -scan_code if scan_code < 0 else user32.MapVirtualKeyW(scan_code, MAPVK_VSC_TO_VK_EX)
    if not vk:
        return True  # не смогли определить — не трогаем, чтобы не снять живую
    if user32.GetAsyncKeyState(vk) & 0x8000:
        return True
    # Скан-код не различает левый и правый модификатор, поэтому проверяем ещё и
    # обобщённый VK — иначе снимем реально зажатый правый Ctrl/Alt/Shift.
    generic = _SIDED_VK.get(vk)
    return bool(generic and (user32.GetAsyncKeyState(generic) & 0x8000))


def keyboard_watchdog_loop() -> None:
    while not stop_event.wait(WATCHDOG_INTERVAL):
        try:
            with keyboard._pressed_events_lock:
                stuck = [sc for sc in list(keyboard._pressed_events)
                         if not _is_physically_pressed(sc)]
                for sc in stuck:
                    keyboard._pressed_events.pop(sc, None)
                    keyboard._logically_pressed_keys.pop(sc, None)
                    keyboard._listener.active_modifiers.discard(sc)
            if stuck:
                log_error(f"watchdog: сняты залипшие клавиши {stuck}")

            # Флаги AltGr в _winkeyboard живут отдельно от набора нажатых клавиш
            # и тоже залипают: ignore_next_right_alt съедает следующий правый Alt.
            if not (ctypes.windll.user32.GetAsyncKeyState(VK_MENU) & 0x8000):
                _winkeyboard.altgr_is_pressed = False
                _winkeyboard.ignore_next_right_alt = False
            if not (ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000):
                _winkeyboard.shift_is_pressed = False
        except Exception as e:
            log_error(f"watchdog: {e}")


# ============================================================
# Самопроверка горячих клавиш и перезапуск
# ============================================================
# Watchdog выше лечит только один сбой — залипшую клавишу. Но 04.08.2026
# хоткеи отвалились при полностью здоровом с виду процессе: потоки живы, хук
# получает события, залипших клавиш нет, очередь разбирается — а обработчик
# хоткея не вызывается. Причину внутри keyboard найти не удалось, зато сбой
# надёжно виден снаружи: посланная себе клавиша не доходит до обработчика.
# Ниже — проверка ровно этого пути и перезапуск, если он оборван.
_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", _ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class _INPUTUNION(ctypes.Union):
    # Союз обязан включать самый большой вариант (mouse), иначе размер структуры
    # не сойдётся с тем, что ждёт SendInput, и он вернёт ERROR_INVALID_PARAMETER.
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


def _on_heartbeat() -> None:
    _heartbeat_seen.set()


def _send_heartbeat_key() -> int:
    user32 = ctypes.windll.user32
    events = (_INPUT * 2)()
    events[0].type = 1
    events[0].ki = _KEYBDINPUT(HEARTBEAT_VK, 0, 0, 0, 0)
    events[1].type = 1
    events[1].ki = _KEYBDINPUT(HEARTBEAT_VK, 0, 0x0002, 0, 0)  # KEYEVENTF_KEYUP
    return user32.SendInput(2, ctypes.byref(events), ctypes.sizeof(_INPUT))


def _input_desktop_available() -> bool:
    """False на защищённом рабочем столе (UAC) и экране блокировки.

    Там наш хук ввода не видит вообще ничего — это не поломка, и перезапуск
    делу не поможет, поэтому проверку в такие моменты просто пропускаем.
    """
    user32 = ctypes.windll.user32
    desktop = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_READOBJECTS
    if not desktop:
        return False
    user32.CloseDesktop(desktop)
    return True


def _hotkeys_alive() -> bool:
    _heartbeat_seen.clear()
    try:
        if not _send_heartbeat_key():
            return True  # не смогли послать — судить не о чем
    except Exception as e:
        log_error(f"heartbeat send: {e}")
        return True
    return _heartbeat_seen.wait(HEARTBEAT_TIMEOUT)


def heartbeat_loop() -> None:
    fails = 0
    while not stop_event.wait(HEARTBEAT_INTERVAL):
        try:
            if not _input_desktop_available():
                continue
            if _hotkeys_alive():
                fails = 0
                continue
            fails += 1
            log_error(f"самопроверка: горячие клавиши не отвечают ({fails})")
            if fails >= HEARTBEAT_FAILS_BEFORE_RESTART:
                log_error("самопроверка: перезапускаюсь")
                restart_app(quiet=True)
                return
        except Exception as e:
            log_error(f"heartbeat_loop: {e}")
            fails = 0


def _restart_command() -> list:
    py = sys.executable
    pyw = py.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = py
    return [pyw, os.path.abspath(__file__), RESTART_FLAG]


def restart_app(quiet: bool = False) -> None:
    """Поднимает свежую копию и гасит текущую.

    Новая копия стартует с RESTART_FLAG и подождёт, пока мы отпустим мьютекс,
    иначе она решит, что программа уже запущена, и молча закроется.
    """
    try:
        subprocess.Popen(
            _restart_command(),
            close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as e:
        log_error(f"restart: {e}")
        if not quiet:
            notify(t('notify.restart_failed'))
        return

    stop_event.set()
    try:
        keyboard.remove_all_hotkeys()
    except Exception:
        pass
    if icon_ref is not None:
        try:
            icon_ref.stop()
        except Exception:
            pass


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
            notify(t('notify.log_empty'))
    except Exception as e:
        log_error(f"open_log: {e}")


def menu_toggle_resize(icon, item):
    new_value = not get_config("auto_resize", True)
    set_config("auto_resize", new_value)
    notify(t('notify.autoresize_on' if new_value else 'notify.autoresize_off'))


def menu_set_prefix(icon, item):
    action_queue.put('set_prefix')


def _prefix_menu_text(item) -> str:
    p = get_config("filename_prefix", "") or ""
    if not p:
        return t('menu.prefix_none')
    shown = p if len(p) <= 25 else p[:22] + '…'
    return t('menu.prefix', value=shown)


def menu_toggle_autostart(icon, item):
    new_value = not is_autostart_enabled()
    set_autostart(new_value)
    notify(t('notify.autostart_on' if new_value else 'notify.autostart_off'))


def _make_language_setter(code: str):
    def setter(icon, item):
        set_language(code)
        try:
            icon.update_menu()
        except Exception:
            pass
        notify(t('notify.language_changed'))
    return setter


def _make_format_setter(fmt: str):
    def setter(icon, item):
        set_config("image_format", fmt)
        try:
            icon.update_menu()
        except Exception:
            pass
        notify(t('notify.format_changed', fmt=fmt.upper()))
    return setter


def _build_format_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(
            'PNG', _make_format_setter('png'),
            radio=True, checked=lambda item: get_format() == 'png',
        ),
        pystray.MenuItem(
            'JPEG', _make_format_setter('jpeg'),
            radio=True, checked=lambda item: get_format() == 'jpeg',
        ),
    )


def menu_restart(icon, item):
    restart_app()


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


def _make_hotkey_setter(action: str):
    def setter(icon, item):
        action_queue.put(f'set_hotkey:{action}')
    return setter


def _build_hotkeys_menu() -> pystray.Menu:
    return pystray.Menu(*[
        pystray.MenuItem(
            (lambda a: lambda item: f"{t('action.' + a)}: {_pretty_hotkey(get_hotkey(a))}")(action),
            _make_hotkey_setter(action),
        )
        for action in ('dialog', 'quick', 'area', 'ocr')
    ])


def _make_cleanup_setter(days: int):
    def setter(icon, item):
        set_config("cleanup_days", days)
        try:
            icon.update_menu()
        except Exception:
            pass
        if days:
            notify(t('notify.cleanup_on', days=days, count=cleanup_old_screenshots()))
        else:
            notify(t('notify.cleanup_off'))
    return setter


def _build_cleanup_menu() -> pystray.Menu:
    return pystray.Menu(*[
        pystray.MenuItem(
            (lambda d: lambda item: t('menu.cleanup_never') if d == 0
             else t('menu.cleanup_days', days=d))(days),
            _make_cleanup_setter(days),
            radio=True,
            checked=(lambda d: lambda item: get_config("cleanup_days", 0) == d)(days),
        )
        for days in CLEANUP_CHOICES
    ])


def _build_language_menu() -> pystray.Menu:
    items = []
    for code, table in I18N.items():
        label = table.get('lang.name', code)
        items.append(pystray.MenuItem(
            label,
            _make_language_setter(code),
            radio=True,
            checked=(lambda c: lambda item: get_language() == c)(code),
        ))
    return pystray.Menu(*items)


def build_menu():
    return pystray.Menu(
        pystray.MenuItem(lambda item: t('menu.title'), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: t('menu.hotkeys'), _build_hotkeys_menu()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_prefix_menu_text, menu_set_prefix),
        pystray.MenuItem(lambda item: t('menu.format'), _build_format_menu()),
        pystray.MenuItem(lambda item: t('menu.cleanup'), _build_cleanup_menu()),
        pystray.MenuItem(
            lambda item: t('menu.autoresize', px=MAX_DIMENSION),
            menu_toggle_resize,
            checked=lambda item: get_config("auto_resize", True),
        ),
        pystray.MenuItem(
            lambda item: t('menu.autostart'),
            menu_toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.MenuItem(lambda item: t('menu.language'), _build_language_menu()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: t('menu.open_folder'), menu_open_screenshots, default=True),
        pystray.MenuItem(lambda item: t('menu.open_log'), menu_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: t('menu.restart'), menu_restart),
        pystray.MenuItem(lambda item: t('menu.exit'), menu_exit),
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

    # Защита от двойного запуска. При перезапуске старая копия ещё догорает и
    # держит мьютекс, поэтому даём ей время уйти, а не рапортуем «уже запущен».
    deadline = time.monotonic() + (RESTART_WAIT if RESTART_FLAG in sys.argv else 0.0)
    while True:
        _mutex_handle = win32event.CreateMutex(None, False, MUTEX_NAME)
        if win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS:
            break
        try:
            win32api.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None
        if time.monotonic() >= deadline:
            ctypes.windll.user32.MessageBoxW(
                0,
                t('msg.already_running'),
                APP_TITLE,
                0x40,
            )
            sys.exit(0)
        time.sleep(0.25)

    try:
        os.makedirs(DEFAULT_SCREENSHOTS_DIR, exist_ok=True)
    except Exception as e:
        log_error(f"main mkdir: {e}")

    register_hotkeys()

    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()

    threading.Thread(target=keyboard_watchdog_loop, daemon=True).start()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()

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
