"""Batch TTS audio generation using Google Chirp 3 HD."""

from __future__ import annotations

import hashlib

from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech

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
