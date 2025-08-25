import os
import json
import queue
import socket
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
import numpy as np
import soundfile as sf

from faster_whisper import WhisperModel
from command_parser import parse_command


# -----------------------------
# Config & Globals
# -----------------------------

def get_secret_bool(name: str, default: bool) -> bool:
    val = st.secrets.get(name, os.getenv(name, str(default))).__str__().lower()
    return val in ("1", "true", "yes", "y", "on")

SIMULATOR_MODE = get_secret_bool("SIMULATOR_MODE", True)
BRIDGE_HOST = st.secrets.get("BRIDGE_HOST", os.getenv("BRIDGE_HOST", "127.0.0.1"))
BRIDGE_PORT = int(st.secrets.get("BRIDGE_PORT", os.getenv("BRIDGE_PORT", "8765")))

USE_EXTERNAL_LLM = get_secret_bool("USE_EXTERNAL_LLM", False)
EXTERNAL_LLM_BASE_URL = st.secrets.get("EXTERNAL_LLM_BASE_URL", os.getenv("EXTERNAL_LLM_BASE_URL", ""))
EXTERNAL_LLM_API_KEY = st.secrets.get("EXTERNAL_LLM_API_KEY", os.getenv("EXTERNAL_LLM_API_KEY", ""))

st.set_page_config(page_title="Voice Smart Home (No OpenAI)", page_icon="🎙️")
st.title("🎙️ Voice‑Controlled Smart Home Assistant (No OpenAI)")
st.caption("Whisper STT → Deterministic command parser → Arduino via socket or simulator")

# Session state to store audio buffers and simulated GPIO
if "audio_frames" not in st.session_state:
    st.session_state.audio_frames = []
if "sim_gpio" not in st.session_state:
    st.session_state.sim_gpio = {
        "light:living_room": False,
        "light:kitchen": False,
        "fan:kitchen": False,
        "garage:door": "closed",
        "thermostat:home": 72,
    }

# -----------------------------
# Audio capture (WebRTC)
# -----------------------------

class AudioProcessor(AudioProcessorBase):
    def __init__(self) -> None:
        self._buffer = queue.Queue()

    def recv_audio(self, frame):
        # frame: av.AudioFrame -> ndarray float32 [-1.0, 1.0]
        data = frame.to_ndarray().flatten()
        self._buffer.put(data)
        return frame

    def get_all_audio(self) -> Optional[np.ndarray]:
        chunks = []
        try:
            while True:
                chunks.append(self._buffer.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            return np.concatenate(chunks)
        return None


st.sidebar.header("Settings")
model_size = st.sidebar.selectbox("Whisper model size", ["tiny", "base"], index=0)
compute_type = st.sidebar.selectbox("Compute type", ["int8", "int8_float16", "float32"], index=0)
language = st.sidebar.text_input("Language hint (e.g., en)", value="en")
st.sidebar.write("**Mode:**", "SIMULATOR" if SIMULATOR_MODE else "HARDWARE (socket→Arduino)")

# Lazy-load Whisper (cache across reruns)
@st.cache_resource(show_spinner=True)
def load_whisper_model(size: str, compute: str):
    return WhisperModel(size, compute_type=compute)

whisper = load_whisper_model(model_size, compute_type)

# -----------------------------
# UI: Mic or File upload
# -----------------------------
st.subheader("1) Capture Audio")
tab_mic, tab_upload = st.tabs(["🎤 Microphone", "📁 Upload Audio"])

with tab_mic:
    st.write("Click **Start** to capture mic audio, then **Stop** and **Transcribe & Execute**.")
    ctx = webrtc_streamer(
        key="stt",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        media_stream_constraints={"audio": True, "video": False},
        async_processing=True,
        audio_processor_factory=AudioProcessor,
    )

    if ctx.audio_processor:
        if st.button("Stop and buffer mic audio"):
            audio = ctx.audio_processor.get_all_audio()
            if audio is not None:
                st.session_state.audio_frames.append(audio)
                st.success(f"Captured {len(audio)} samples from mic.")

with tab_upload:
    up = st.file_uploader("Upload WAV/MP3/M4A", type=["wav", "mp3", "m4a"])
    if up is not None:
        data = up.read()
        # Save raw bytes to temp WAV for uniform processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpf:
            tmp_path = tmpf.name
        # Use soundfile to re-encode
        with sf.SoundFile(tmp_path, mode="w", samplerate=16000, channels=1, subtype="PCM_16") as f:
            # Decode with soundfile directly from bytes may not always work; fallback: write then reload
            # Here we assume small files; simply try to decode via pydub to a mono 16k array if needed.
            import io
            import pydub
            segment = pydub.AudioSegment.from_file(io.BytesIO(data))
            segment = segment.set_channels(1).set_frame_rate(16000)
            samples = np.array(segment.get_array_of_samples()).astype(np.int16)
            f.write(samples)
        # Load into frames buffer as float32
        samples_f32, _ = sf.read(tmp_path, dtype="float32")
        st.session_state.audio_frames.append(samples_f32)
        st.success("Uploaded audio buffered.")

# -----------------------------
# Transcription
# -----------------------------
st.subheader("2) Transcribe & Parse")
if st.button("Transcribe & Execute"):
    if not st.session_state.audio_frames:
        st.warning("No audio buffered yet. Use the mic or upload a file.")
        st.stop()

    # Merge all buffered audio into one stream (mono, 16k)
    audio = np.concatenate(st.session_state.audio_frames)
    # Write to temp WAV for Whisper
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wavf:
        wav_path = wavf.name
    sf.write(wav_path, audio, 16000)

    with st.spinner("Transcribing with Whisper (CPU)…"):
        segments, info = whisper.transcribe(wav_path, language=language or None)
        transcript = "".join([seg.text for seg in segments]).strip()

    st.write("**Transcript:**")
    st.code(transcript or "(empty)")

    # Parse command
    intent = parse_command(transcript)
    st.write("**Parsed command:**")
    st.json(intent)

    # Execute
    result = None
    if SIMULATOR_MODE:
        result = f"[SIMULATOR] {intent}"
        # Update simulated GPIO
        device = intent.get("device")
        action = intent.get("action")
        location = intent.get("location") or "home"
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

        st.success("Executed in SIMULATOR.")
    else:
        with st.spinner(f"Sending to bridge at {BRIDGE_HOST}:{BRIDGE_PORT}…"):
            payload = json.dumps(intent).encode("utf-8")
            try:
                with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=3) as s:
                    s.sendall(payload + b"\n")
                result = "Sent to local device bridge."
                st.success(result)
            except Exception as e:
                st.error(f"Failed to reach bridge: {e}")
                st.stop()

    st.subheader("3) Result")
    st.write(result or "No result.")
    if SIMULATOR_MODE:
        st.write("**Simulator GPIO state:**")
        st.json(st.session_state.sim_gpio)

    # Clear buffered audio
    st.session_state.audio_frames = []

st.divider()
st.caption("Powered by faster‑whisper (no OpenAI). Optional non‑OpenAI LLM hook available but disabled by default.")
