import os
import io
import json
import socket
import tempfile
from typing import Optional, Dict, Any

import streamlit as st
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from faster_whisper import WhisperModel
from streamlit_mic_recorder import mic_recorder

from command_parser import parse_command

# -----------------------------
# Config & Branding
# -----------------------------
def _get_secret_bool(name: str, default: bool) -> bool:
    raw = None
    try:
        raw = st.secrets.get(name)
    except Exception:
        pass
    if raw is None:
        raw = os.getenv(name, str(default))
    return str(raw).lower() in ("1", "true", "yes", "y", "on")

SIMULATOR_MODE = _get_secret_bool("SIMULATOR_MODE", True)
BRIDGE_HOST = st.secrets.get("BRIDGE_HOST", os.getenv("BRIDGE_HOST", "127.0.0.1"))
BRIDGE_PORT = int(st.secrets.get("BRIDGE_PORT", os.getenv("BRIDGE_PORT", "8765")))

st.set_page_config(page_title="Voice Smart Home", page_icon="🎙️")
st.title("🎙️ Voice-Controlled Smart Home Assistant")
st.caption("Powered by ZARI")

if "sim_gpio" not in st.session_state:
    st.session_state.sim_gpio = {
        "light:living room": False,
        "light:kitchen": False,
        "fan:kitchen": False,
        "garage:door": "closed",
        "thermostat:home": 72,
    }

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.header("Settings")
model_size = st.sidebar.selectbox("Whisper model size", ["tiny", "base"], index=0)
compute_type = st.sidebar.selectbox("Compute type", ["int8", "int8_float16", "float32"], index=0)
lang_choice = st.sidebar.selectbox("Language", ["auto", "en", "es"], index=0)
st.sidebar.write("**Mode:**", "SIMULATOR" if SIMULATOR_MODE else "HARDWARE (socket→Arduino)")

@st.cache_resource(show_spinner=True)
def load_whisper_model(size: str, compute: str):
    # CPU-friendly
    return WhisperModel(size, compute_type=compute)

whisper = load_whisper_model(model_size, compute_type)

def _normalize_to_wav_16k_mono_bytes(blob: bytes) -> bytes:
    """Return WAV bytes (mono, 16k, PCM16) from input audio bytes."""
    seg = AudioSegment.from_file(io.BytesIO(blob))
    seg = seg.set_channels(1).set_frame_rate(16000)
    samples = np.array(seg.get_array_of_samples()).astype(np.int16)
    out = io.BytesIO()
    sf.write(out, samples, 16000, subtype="PCM_16", format="WAV")
    return out.getvalue()

def _transcribe(wav_path: str, lang_hint: Optional[str]) -> Dict[str, Any]:
    segments, info = whisper.transcribe(
        wav_path,
        language=None if (lang_hint in (None, "", "auto")) else lang_hint
    )
    transcript = "".join([s.text for s in segments]).strip()
    return {"text": transcript, "detected_lang": getattr(info, "language", None)}

# -----------------------------
# 1) Capture Audio
# -----------------------------
st.subheader("1) Capture Audio")

tab_mic, tab_upload = st.tabs(["🎤 Microphone", "📁 Upload Audio"])

audio_bytes: Optional[bytes] = None

with tab_mic:
    st.write("Click **Start** to record, then **Stop**. Use **Transcribe & Execute** below.")
    rec = mic_recorder(
        start_prompt="Start",
        stop_prompt="Stop",
        just_once=True,
        use_container_width=True,
        format="wav",  # returns WAV bytes
        key="zari_mic",
    )
    if rec and isinstance(rec, dict) and rec.get("bytes"):
        audio_bytes = rec["bytes"]
        st.success("Microphone audio captured.")
        st.audio(audio_bytes, format="audio/wav")

with tab_upload:
    up = st.file_uploader("Upload WAV/MP3/M4A", type=["wav", "mp3", "m4a"])
    if up is not None:
        audio_bytes = up.read()
        st.success(f"Loaded {up.name} ({len(audio_bytes)/1024:.1f} KB)")

# -----------------------------
# 2) Transcribe & Parse
# -----------------------------
st.subheader("2) Transcribe & Parse")
run = st.button("Transcribe & Execute", type="primary", disabled=(audio_bytes is None))

if run:
    if audio_bytes is None:
        st.warning("No audio yet. Record or upload first.")
        st.stop()

    # Normalize to mono 16k WAV for Whisper
    with st.spinner("Transcribing…"):
        try:
            wav_norm = _normalize_to_wav_16k_mono_bytes(audio_bytes)
        except Exception as e:
            st.error(f"Unable to read audio: {e}")
            st.stop()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpf:
            tmpf.write(wav_norm)
            wav_path = tmpf.name

        tx = _transcribe(wav_path, lang_choice)
        transcript = tx["text"]
        detected_lang = tx["detected_lang"]

    st.write("**Transcript**")
    st.code(transcript or "(empty)")

    # Parse (English + Spanish supported)
    intent = parse_command(transcript)
    st.write("**Parsed command**")
    st.json(intent)

    # Execute
    if SIMULATOR_MODE:
        device = intent.get("device")
        action = intent.get("action")
        location = (intent.get("location") or "home")
        value = intent.get("value")

        key = None
        if device in ("light", "fan"):
            key = f"{device}:{location}"
            if action in ("on", "off"):
                st.session_state.sim_gpio[key] = (action == "on")
        elif device == "thermostat":
            key = "thermostat:home"
            if isinstance(value, (int, float)):
                st.session_state.sim_gpio[key] = int(value)
        elif device == "garage":
            key = "garage:door"
            if action in ("open", "close"):
                st.session_state.sim_gpio[key] = "open" if action == "open" else "closed"

        st.success("Executed (SIMULATOR).")
        st.write("**Simulator GPIO state**")
        st.json(st.session_state.sim_gpio)
    else:
        try:
            payload = json.dumps(intent).encode("utf-8")
            with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=3) as s:
                s.sendall(payload + b"\n")
            st.success(f"Sent to bridge at {BRIDGE_HOST}:{BRIDGE_PORT}")
        except Exception as e:
            st.error(f"Failed to reach bridge: {e}")

st.divider()
st.caption("Tip: For Spanish, set ‘Language’ to **es** or leave **auto** (model will detect).")
