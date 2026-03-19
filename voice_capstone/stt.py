"""
Speech-to-Text module for ClinAssist
Uses whisper-1 model via Nexus API for audio transcription
"""
import time
import requests
import base64
import io
from requests.adapters import HTTPAdapter
from typing import Optional
from config import (
    NEXUS_BASE_URL,
    NEXUS_API_KEY,
    NEXUS_STT_PATH,
    STT_MODEL,
    STT_REQUEST_MODE,
    STT_TIMEOUT_SECONDS,
)
from database import log_latency


HTTP_SESSION = requests.Session()
HTTP_ADAPTER = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
HTTP_SESSION.mount("http://", HTTP_ADAPTER)
HTTP_SESSION.mount("https://", HTTP_ADAPTER)


def transcribe_audio(audio_bytes: bytes, session_id: str) -> str:
    """
    Transcribe audio to text using whisper-1 via Nexus API
    
    Args:
        audio_bytes: Raw audio bytes (WAV format, 16kHz, 16-bit PCM mono)
        session_id: Session ID for latency logging
    
    Returns:
        Transcribed text string (empty string on error)
    """
    start_time = time.time()

    if not NEXUS_API_KEY or not NEXUS_BASE_URL:
        print("STT configuration missing: set NEXUS_API_KEY/NEXUS_BASE_URL (or API_KEY/BASE_URL).")
        latency_ms = (time.time() - start_time) * 1000
        log_latency(session_id, "stt_error", latency_ms)
        return ""

    def _extract_text(response: requests.Response) -> str:
        try:
            result = response.json()
            if isinstance(result, dict):
                return (result.get("text") or result.get("transcript") or "").strip()
            if isinstance(result, str):
                return result.strip()
            return ""
        except Exception:
            raw = response.text.strip()
            if raw:
                return raw
            return ""

    # Attempt 1: Standard multipart Whisper-style upload in-memory (no disk I/O)
    if STT_REQUEST_MODE in {"auto", "multipart"}:
        try:
            headers = {"Authorization": f"Bearer {NEXUS_API_KEY}"}
            data = {
                "model": STT_MODEL,
                "response_format": "json",
                "language": "en"
            }

            wav_stream = io.BytesIO(audio_bytes)
            files = {"file": ("audio.wav", wav_stream, "audio/wav")}
            response = HTTP_SESSION.post(
                f"{NEXUS_BASE_URL}{NEXUS_STT_PATH}",
                data=data,
                files=files,
                headers=headers,
                timeout=STT_TIMEOUT_SECONDS
            )

            response.raise_for_status()
            transcript = _extract_text(response)

            latency_ms = (time.time() - start_time) * 1000
            log_latency(session_id, "stt", latency_ms)

            if transcript:
                return transcript

        except requests.exceptions.RequestException as e:
            error_body = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    error_body = resp.text
                except Exception:
                    error_body = ""
            print(f"STT API Error (multipart): {e} | Response: {error_body}")

            if STT_REQUEST_MODE == "multipart":
                latency_ms = (time.time() - start_time) * 1000
                log_latency(session_id, "stt_error", latency_ms)
                return ""

        except Exception as e:
            print(f"STT Error (multipart): {e}")
            if STT_REQUEST_MODE == "multipart":
                latency_ms = (time.time() - start_time) * 1000
                log_latency(session_id, "stt_error", latency_ms)
                return ""

        finally:
            pass

    # Attempt 2: JSON/base64 fallback for custom gateways
    if STT_REQUEST_MODE in {"auto", "json"}:
        try:
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            payload = {
                "model": STT_MODEL,
                "audio": audio_base64,
                "response_format": "json",
                "language": "en"
            }
            headers = {
                "Authorization": f"Bearer {NEXUS_API_KEY}",
                "Content-Type": "application/json"
            }

            response = HTTP_SESSION.post(
                f"{NEXUS_BASE_URL}{NEXUS_STT_PATH}",
                json=payload,
                headers=headers,
                timeout=STT_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            transcript = _extract_text(response)

            latency_ms = (time.time() - start_time) * 1000
            log_latency(session_id, "stt", latency_ms)

            if transcript:
                return transcript

        except requests.exceptions.RequestException as e:
            error_body = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    error_body = resp.text
                except Exception:
                    error_body = ""
            print(f"STT API Error (json fallback): {e} | Response: {error_body}")

        except Exception as e:
            print(f"STT Error (json fallback): {e}")

    latency_ms = (time.time() - start_time) * 1000
    log_latency(session_id, "stt_error", latency_ms)
    return ""


def validate_audio_format(audio_bytes: bytes) -> bool:
    """
    Validate that audio is in WAV format
    Simple check for WAV header (RIFF)
    
    Args:
        audio_bytes: Raw audio bytes
    
    Returns:
        True if valid WAV format, False otherwise
    """
    if len(audio_bytes) < 44:
        return False
    
    # Check for RIFF header
    if audio_bytes[0:4] != b'RIFF':
        return False
    
    # Check for WAVE format
    if audio_bytes[8:12] != b'WAVE':
        return False
    
    return True
