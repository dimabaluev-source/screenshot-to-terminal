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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — save via dialog',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — quick save to Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — capture screen area',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (text from clipboard image)',
        'menu.prefix_none': 'Filename prefix: (none)',
        'menu.prefix': 'Filename prefix: {value}',
        'menu.autoresize': 'Auto-resize large (>{px}px)',
        'menu.autostart': 'Autostart with Windows',
        'menu.format': 'Save format',
        'menu.open_folder': 'Open screenshots folder',
        'menu.open_log': 'Open error log',
        'menu.language': 'Language',
        'menu.exit': 'Exit',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — сохранить через диалог',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — быстро в Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — захват области экрана',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (текст из картинки в буфере)',
        'menu.prefix_none': 'Префикс имени: (нет)',
        'menu.prefix': 'Префикс имени: {value}',
        'menu.autoresize': 'Авторесайз больших (>{px}px)',
        'menu.autostart': 'Автозапуск с Windows',
        'menu.format': 'Формат сохранения',
        'menu.open_folder': 'Открыть папку скриншотов',
        'menu.open_log': 'Открыть лог ошибок',
        'menu.language': 'Язык',
        'menu.exit': 'Выход',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — 通过对话框保存',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — 快速保存到 Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — 截取屏幕区域',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR（从剪贴板图片提取文本）',
        'menu.prefix_none': '文件名前缀：（无）',
        'menu.prefix': '文件名前缀：{value}',
        'menu.autoresize': '自动缩放大图（>{px}px）',
        'menu.autostart': '开机自启动',
        'menu.format': '保存格式',
        'menu.open_folder': '打开截图文件夹',
        'menu.open_log': '打开错误日志',
        'menu.language': '语言',
        'menu.exit': '退出',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — ダイアログで保存',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — Pictures\\Screenshots にすぐ保存',
        'menu.hotkey_area': 'Ctrl+Alt+A — 画面範囲をキャプチャ',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR（クリップボード画像からテキスト）',
        'menu.prefix_none': 'ファイル名プレフィックス：（なし）',
        'menu.prefix': 'ファイル名プレフィックス：{value}',
        'menu.autoresize': '大きい画像を自動リサイズ（>{px}px）',
        'menu.autostart': 'Windows と一緒に自動起動',
        'menu.format': '保存形式',
        'menu.open_folder': 'スクリーンショットフォルダを開く',
        'menu.open_log': 'エラーログを開く',
        'menu.language': '言語',
        'menu.exit': '終了',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — über Dialog speichern',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — schnell in Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — Bildschirmbereich erfassen',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (Text aus Bild in Zwischenablage)',
        'menu.prefix_none': 'Dateinamen-Präfix: (keins)',
        'menu.prefix': 'Dateinamen-Präfix: {value}',
        'menu.autoresize': 'Große automatisch verkleinern (>{px}px)',
        'menu.autostart': 'Mit Windows starten',
        'menu.format': 'Speicherformat',
        'menu.open_folder': 'Screenshot-Ordner öffnen',
        'menu.open_log': 'Fehlerprotokoll öffnen',
        'menu.language': 'Sprache',
        'menu.exit': 'Beenden',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — salva tramite finestra',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — salvataggio rapido in Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — cattura area dello schermo',
        'menu.hotkey_ocr': "Ctrl+Alt+D — OCR (testo dall'immagine negli appunti)",
        'menu.prefix_none': 'Prefisso nome file: (nessuno)',
        'menu.prefix': 'Prefisso nome file: {value}',
        'menu.autoresize': 'Ridimensiona immagini grandi (>{px}px)',
        'menu.autostart': 'Avvia con Windows',
        'menu.format': 'Formato di salvataggio',
        'menu.open_folder': 'Apri cartella screenshot',
        'menu.open_log': 'Apri registro errori',
        'menu.language': 'Lingua',
        'menu.exit': 'Esci',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — guardar con diálogo',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — guardado rápido en Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — capturar área de pantalla',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (texto de la imagen del portapapeles)',
        'menu.prefix_none': 'Prefijo del nombre: (ninguno)',
        'menu.prefix': 'Prefijo del nombre: {value}',
        'menu.autoresize': 'Reducir imágenes grandes (>{px}px)',
        'menu.autostart': 'Iniciar con Windows',
        'menu.format': 'Formato de guardado',
        'menu.open_folder': 'Abrir carpeta de capturas',
        'menu.open_log': 'Abrir registro de errores',
        'menu.language': 'Idioma',
        'menu.exit': 'Salir',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — enregistrer via la boîte de dialogue',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — enregistrement rapide dans Pictures\\Screenshots',
        'menu.hotkey_area': "Ctrl+Alt+A — capturer une zone de l'écran",
        'menu.hotkey_ocr': "Ctrl+Alt+D — OCR (texte de l'image du presse-papiers)",
        'menu.prefix_none': 'Préfixe du nom : (aucun)',
        'menu.prefix': 'Préfixe du nom : {value}',
        'menu.autoresize': 'Réduire les grandes images (>{px}px)',
        'menu.autostart': 'Démarrer avec Windows',
        'menu.format': "Format d'enregistrement",
        'menu.open_folder': 'Ouvrir le dossier des captures',
        'menu.open_log': 'Ouvrir le journal des erreurs',
        'menu.language': 'Langue',
        'menu.exit': 'Quitter',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — salvar via caixa de diálogo',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — salvar rápido em Pictures\\Screenshots',
        'menu.hotkey_area': 'Ctrl+Alt+A — capturar área da tela',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (texto da imagem na área de transferência)',
        'menu.prefix_none': 'Prefixo do nome: (nenhum)',
        'menu.prefix': 'Prefixo do nome: {value}',
        'menu.autoresize': 'Redimensionar imagens grandes (>{px}px)',
        'menu.autostart': 'Iniciar com o Windows',
        'menu.format': 'Formato de salvamento',
        'menu.open_folder': 'Abrir pasta de capturas',
        'menu.open_log': 'Abrir registro de erros',
        'menu.language': 'Idioma',
        'menu.exit': 'Sair',
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
        'menu.hotkey_dialog': 'Ctrl+Alt+S — 대화 상자로 저장',
        'menu.hotkey_quick': 'Ctrl+Alt+Shift+S — Pictures\\Screenshots에 빠른 저장',
        'menu.hotkey_area': 'Ctrl+Alt+A — 화면 영역 캡처',
        'menu.hotkey_ocr': 'Ctrl+Alt+D — OCR (클립보드 이미지에서 텍스트)',
        'menu.prefix_none': '파일 이름 접두사: (없음)',
        'menu.prefix': '파일 이름 접두사: {value}',
        'menu.autoresize': '큰 이미지 자동 축소 (>{px}px)',
        'menu.autostart': 'Windows와 함께 시작',
        'menu.format': '저장 형식',
        'menu.open_folder': '스크린샷 폴더 열기',
        'menu.open_log': '오류 로그 열기',
        'menu.language': '언어',
        'menu.exit': '종료',
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

    state = {'start': None, 'bbox': None, 'after_id': None, 'last': None}

    def set_selection(cx1, cy1, cx2, cy2):
        cx1, cx2 = sorted((cx1, cx2))
        cy1, cy2 = sorted((cy1, cy2))
        cx1 = max(0, min(virtual_w, cx1))
        cy1 = max(0, min(virtual_h, cy1))
        cx2 = max(0, min(virtual_w, cx2))
        cy2 = max(0, min(virtual_h, cy2))
        canvas.coords(hole, cx1, cy1, cx2, cy2)
        canvas.coords(sel_rect, cx1, cy1, cx2, cy2)

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
        pystray.MenuItem(lambda item: t('menu.hotkey_dialog'), None, enabled=False),
        pystray.MenuItem(lambda item: t('menu.hotkey_quick'), None, enabled=False),
        pystray.MenuItem(lambda item: t('menu.hotkey_area'), None, enabled=False),
        pystray.MenuItem(lambda item: t('menu.hotkey_ocr'), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_prefix_menu_text, menu_set_prefix),
        pystray.MenuItem(lambda item: t('menu.format'), _build_format_menu()),
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

    # Защита от двойного запуска
    _mutex_handle = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0,
            t('msg.already_running'),
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
