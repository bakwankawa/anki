# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Batch TTS audio generation using Google Chirp 3 HD."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech

from anki.collection import Collection
from anki.notes import NoteId
from anki.utils import strip_html
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (
    QAction,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo, showWarning, tooltip

VOICE_NAME = "en-US-Chirp3-HD-Achernar"
LANGUAGE_CODE = "en-US"
SAMPLE_RATE_HZ = 44100
SPEAKING_RATE = 1.0
VOLUME_GAIN_DB = 0.0


def synthesize_audio(text: str, api_key: str) -> bytes:
    """Synthesize speech from text using Google Chirp 3 HD.

    Returns MP3 audio bytes.
    """
    client = texttospeech.TextToSpeechClient(
        client_options=ClientOptions(api_key=api_key)
    )
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code=LANGUAGE_CODE,
            name=VOICE_NAME,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=SPEAKING_RATE,
            volume_gain_db=VOLUME_GAIN_DB,
            sample_rate_hertz=SAMPLE_RATE_HZ,
        ),
    )
    return response.audio_content


def tts_filename(text: str) -> str:
    """Deterministic filename for a given text: tts_{md5}.mp3"""
    md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"tts_{md5}.mp3"


@dataclass
class GenerateTtsConfig:
    source_field: str
    dest_field: str
    api_key: str
    skip_existing: bool


def _load_api_key() -> str:
    """Load saved API key from profile."""
    conf = mw.pm.profile.get("generateTts", {})
    return conf.get("apiKey", "")


def _save_api_key(key: str) -> None:
    """Persist API key to profile."""
    conf = mw.pm.profile.get("generateTts", {})
    conf["apiKey"] = key
    mw.pm.profile["generateTts"] = conf
    mw.pm.save()


def _load_field_prefs(note_type_name: str) -> tuple[str, str]:
    """Load last-used source/dest field names for a note type."""
    conf = mw.pm.profile.get("generateTts", {})
    fields = conf.get("fields", {})
    prefs = fields.get(note_type_name, {})
    return prefs.get("source", ""), prefs.get("dest", "")


def _save_field_prefs(note_type_name: str, source: str, dest: str) -> None:
    """Persist last-used field names for a note type."""
    conf = mw.pm.profile.get("generateTts", {})
    fields = conf.get("fields", {})
    fields[note_type_name] = {"source": source, "dest": dest}
    conf["fields"] = fields
    mw.pm.profile["generateTts"] = conf
    mw.pm.save()


class GenerateTtsDialog(QDialog):
    """Dialog for configuring batch TTS generation."""

    def __init__(self, field_names: list[str], note_type_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Audio")
        self.setMinimumWidth(400)
        self._field_names = field_names
        self._note_type_name = note_type_name
        self._config: GenerateTtsConfig | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        form = QFormLayout()

        # Source field
        self._source_combo = QComboBox()
        self._source_combo.addItems(self._field_names)
        form.addRow("Source field:", self._source_combo)

        # Destination field
        self._dest_combo = QComboBox()
        self._dest_combo.addItems(self._field_names)
        form.addRow("Destination field:", self._dest_combo)

        # Restore last-used fields
        saved_source, saved_dest = _load_field_prefs(self._note_type_name)
        if saved_source in self._field_names:
            self._source_combo.setCurrentText(saved_source)
        if saved_dest in self._field_names:
            self._dest_combo.setCurrentText(saved_dest)

        # API key
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setText(_load_api_key())
        self._api_key_edit.setPlaceholderText("Google Cloud API key")

        api_key_row = QVBoxLayout()
        api_key_row.addWidget(self._api_key_edit)
        self._show_key_btn = QPushButton("Show")
        qconnect(self._show_key_btn.clicked, self._toggle_key_visibility)
        api_key_row.addWidget(self._show_key_btn)
        form.addRow("API key:", api_key_row)

        # Skip existing
        self._skip_existing = QCheckBox("Skip cards that already have audio")
        self._skip_existing.setChecked(True)
        form.addRow(self._skip_existing)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._on_accept)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _toggle_key_visibility(self) -> None:
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_key_btn.setText("Hide")
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_key_btn.setText("Show")

    def _on_accept(self) -> None:
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            showWarning("Please enter a Google Cloud API key.")
            return
        source = self._source_combo.currentText()
        dest = self._dest_combo.currentText()

        _save_api_key(api_key)
        _save_field_prefs(self._note_type_name, source, dest)

        self._config = GenerateTtsConfig(
            source_field=source,
            dest_field=dest,
            api_key=api_key,
            skip_existing=self._skip_existing.isChecked(),
        )
        self.accept()

    def get_config(self) -> GenerateTtsConfig | None:
        return self._config


SOUND_TAG_RE = re.compile(r"\[sound:.+?\]")


@dataclass
class GenerationResult:
    generated: int
    skipped: int
    errors: list[str]


def _generate_for_notes(
    col: Collection,
    note_ids: list[NoteId],
    config: GenerateTtsConfig,
) -> GenerationResult:
    """Run in background thread. Generates TTS audio and updates notes."""
    result = GenerationResult(generated=0, skipped=0, errors=[])

    for note_id in note_ids:
        note = col.get_note(note_id)
        field_names = [f["name"] for f in note.note_type()["flds"]]

        if config.source_field not in field_names:
            result.errors.append(
                f"Note {note_id}: missing source field '{config.source_field}'"
            )
            continue
        if config.dest_field not in field_names:
            result.errors.append(
                f"Note {note_id}: missing dest field '{config.dest_field}'"
            )
            continue

        # Read and clean source text
        source_html = note[config.source_field]
        text = strip_html(source_html).strip()
        if not text:
            result.skipped += 1
            continue

        # Check for existing audio in destination field
        if config.skip_existing and SOUND_TAG_RE.search(note[config.dest_field]):
            result.skipped += 1
            continue

        # Compute filename and check if already in media folder
        filename = tts_filename(text)
        media_dir = col.media.dir()
        filepath = os.path.join(media_dir, filename)

        if not os.path.exists(filepath):
            try:
                audio_bytes = synthesize_audio(text, config.api_key)
                col.media.write_data(filename, audio_bytes)
            except Exception as e:
                result.errors.append(f"Note {note_id}: {e}")
                continue

        # Append sound tag to destination field
        sound_tag = f"[sound:{filename}]"
        if sound_tag not in note[config.dest_field]:
            note[config.dest_field] += sound_tag
            col.update_note(note)

        result.generated += 1

    return result


def _on_generate_audio(browser) -> None:
    """Handler for the Generate Audio menu action."""
    note_ids = browser.selected_notes()
    if not note_ids:
        showWarning("Please select one or more cards first.")
        return

    # Get field names from the first selected note
    note = mw.col.get_note(note_ids[0])
    note_type = note.note_type()
    field_names = [f["name"] for f in note_type["flds"]]
    note_type_name = note_type["name"]

    dialog = GenerateTtsDialog(field_names, note_type_name, parent=browser)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    config = dialog.get_config()
    if config is None:
        return

    def on_success(result: GenerationResult) -> None:
        parts = [f"Generated: {result.generated}", f"Skipped: {result.skipped}"]
        if result.errors:
            parts.append(f"Errors: {len(result.errors)}")
            error_detail = "\n".join(result.errors[:20])
            showInfo(
                f"TTS generation complete.\n\n"
                f"{', '.join(parts)}\n\n"
                f"Errors:\n{error_detail}"
            )
        else:
            tooltip(f"TTS done — {', '.join(parts)}", period=3000)

    QueryOp(
        parent=browser,
        op=lambda col: _generate_for_notes(col, list(note_ids), config),
        success=on_success,
    ).with_progress(label="Generating audio...").run_in_background()


def init_generate_tts(browser) -> None:
    """Add 'Generate Audio...' to the browser Edit menu."""
    action = QAction("Generate Audio...", browser)
    qconnect(action.triggered, lambda: _on_generate_audio(browser))
    browser.form.menuEdit.addSeparator()
    browser.form.menuEdit.addAction(action)
