# Batch TTS Audio Generator — Design Spec

## Overview

A new module `qt/aqt/generate_tts.py` that adds a "Generate Audio..." menu item
in the card browser's Edit menu. It generates MP3 audio files using Google
Chirp 3 HD for selected cards and inserts `[sound:...]` tags into a chosen
destination field.

This is a personal-use feature, not intended for upstream contribution.

## User Flow

1. Select cards in the browser
2. Edit > "Generate Audio..."
3. Dialog appears with:
   - **Source field** dropdown — which field contains the English text
   - **Destination field** dropdown — where to insert the `[sound:...]` tag
   - **API key** text input — Google Cloud TTS API key (persisted in Anki config)
   - **Skip existing** checkbox — skip cards that already have a `[sound:...]`
     tag in the destination field (default: checked)
4. Click "Generate"
5. Progress dialog shows while audio is generated in a background thread
6. MP3 files saved to collection media folder, `[sound:filename.mp3]` appended
   to destination field

## Technical Details

### Module

- **File:** `qt/aqt/generate_tts.py`
- **Integration:** Uses `browser_menus_did_init` hook to add menu item — no
  core Anki changes needed

### TTS Engine

- **SDK:** `google-cloud-texttospeech` Python package
- **Voice:** `en-US-Chirp3-HD-Achernar` (hardcoded for v1)
- **Audio config:**
  - Encoding: MP3
  - Sample rate: 44,100 Hz
  - Speaking rate: 1.0
  - Volume gain: 0.0 dB
- **Authentication:** Google Cloud API key, passed via `client_options`

### File Naming

- Format: `tts_{md5(text)}.mp3`
- Deterministic — same text always produces the same filename
- Avoids duplicates: if the file already exists in media folder, skip synthesis

### Dialog (QDialog)

- Dropdowns populated from the note type's field names of the first selected card
- API key field with show/hide toggle
- "Skip existing" checkbox (default: checked)
- "Generate" and "Cancel" buttons

### Threading

- Audio generation runs in a QThread
- Progress dialog with cancel support
- Signals: `progress(int current, int total)`, `finished(list[str] errors)`
- Errors per-card are collected and shown in a summary dialog at the end

### Config Persistence

- API key stored in `mw.pm.profile["generateTts"]["apiKey"]`
- Last-used source/destination field names stored per note type:
  `mw.pm.profile["generateTts"]["fields"][noteTypeName]`

### Card Update

- For each selected card:
  1. Read text from source field, strip HTML tags
  2. Compute filename: `tts_{md5(stripped_text)}.mp3`
  3. If file doesn't exist in media folder, call Google Cloud TTS
  4. Save MP3 bytes to `collection.media/tts_{hash}.mp3`
  5. Append `[sound:tts_{hash}.mp3]` to the destination field
  6. Save the note

### Error Handling

- Invalid/missing API key: show error before starting generation
- Per-card TTS failures (network, quota, etc.): log error, continue to next card
- Summary dialog at the end: "Generated audio for X/Y cards. Z errors."
- Empty source field: skip silently (counted in summary)

### Dependencies

- `google-cloud-texttospeech` — must be pip-installed into the Anki venv

## Out of Scope (v1)

- Language/voice selection (hardcoded to en-US Achernar)
- Right-click context menu integration
- Auto-generation on card save
- Upstream contribution / add-on packaging
