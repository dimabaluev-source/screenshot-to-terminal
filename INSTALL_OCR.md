# Installing Windows OCR language packs

The `Ctrl+Alt+D` (OCR) feature uses **Windows.Media.Ocr** — a recognizer that ships with Windows 10/11 but only handles the languages you've explicitly installed.

By default, this script tries Russian (`ru-RU`) and English (`en-US`) and picks the better result. English is usually preinstalled; other languages need to be added manually.

---

## Check which languages are already supported

Open PowerShell and run:

```powershell
python -c "from winsdk.windows.media.ocr import OcrEngine; from winsdk.windows.globalization import Language; [print(tag, OcrEngine.is_language_supported(Language(tag))) for tag in ['en-US', 'ru-RU', 'de-DE', 'fr-FR', 'es-ES', 'zh-Hans-CN']]"
```

If you see `True` next to the language you need — you're done.

---

## Add a language pack via Settings (GUI, no admin)

1. Open **Settings → Time & language → Language & region**
2. Click **Add a language**
3. Choose the language (Russian, German, Chinese, etc.) → **Next**
4. **Crucial step:** in the "Optional language features" list, make sure **"Optical character recognition"** is checked before clicking **Install**
5. Wait for the download to finish (usually under a minute)
6. Re-run the check command above — your language should now report `True`

You don't need to set the new language as the system language, keyboard layout, or display language. Installing the OCR optional feature alone is enough.

---

## Add a language pack via PowerShell (requires admin)

```powershell
# Russian
Add-WindowsCapability -Online -Name "Language.OCR~~~ru-RU~0.0.1.0"

# German
Add-WindowsCapability -Online -Name "Language.OCR~~~de-DE~0.0.1.0"

# French
Add-WindowsCapability -Online -Name "Language.OCR~~~fr-FR~0.0.1.0"
```

To see all available OCR languages on your edition of Windows:

```powershell
Get-WindowsCapability -Online -Name "Language.OCR*" | Select-Object Name, State
```

---

## Customize which engines the helper tries

By default it tries `('ru-RU', 'en-US')` and picks the better result. To change, edit this line near the top of `screenshot_to_terminal.pyw`:

```python
OCR_LANGUAGES = ('ru-RU', 'en-US')
```

Add or replace with whatever language tags you installed. The script will silently skip any tag that isn't actually installed on your system, so it's safe to list more languages than you have packs for.

---

## Tips for better recognition

- **Tiny text** (below ~12 px) loses accuracy. If you're capturing something small, zoom the source first.
- **Low contrast** (e.g. dark theme with subtle gray-on-gray text) confuses OCR. Try a light theme for that one screenshot.
- **Code** with `l`/`I`/`1` and `O`/`0` is hard for any OCR. For long code blocks, copy text directly when possible; reserve OCR for situations where copy-paste isn't available (terminal recordings, screenshots from a model's response, images on the web, etc.).
- The script already upscales images smaller than 1500 px on the long side before sending them to OCR — this dramatically improves accuracy on small clippings. You can tune this in `_upscale_for_ocr()`.
