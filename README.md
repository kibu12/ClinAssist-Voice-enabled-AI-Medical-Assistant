# ClinAssist - Speech-Driven Structured Clinical Intake System

**Academic Capstone Project**

ClinAssist is a structured pre-screening support tool that collects symptom information through voice or text interaction. This system does not provide medical diagnosis or treatment advice and does not replace a physician.

---

## Overview

ClinAssist uses AI-powered speech recognition and natural language processing to collect structured symptom data through conversational interaction. The system:

* Collects structured symptom attributes via voice or text
* Uses deterministic rule-based risk categorization (no AI diagnosis)
* Generates clinical-style summaries for healthcare providers
* Tracks latency metrics for STT, LLM, and TTS operations
* Includes ASR evaluation using Word Error Rate (WER)

---

## Safety & Scope Limitations

**This system does NOT:**

* Perform medical diagnosis
* Provide treatment advice
* Suggest medication
* Predict diseases
* Use LLM for risk assessment (uses deterministic rules only)

This is an academic demonstration project for structured data collection only.

---

## Tech Stack

| Component      | Technology               | Model            |
| -------------- | ------------------------ | ---------------- |
| Backend        | Python 3.11+, FastAPI    | -                |
| Speech-to-Text | API-based STT            | whisper-1        |
| LLM            | API-based LLM            | gemini-2.5-flash |
| Text-to-Speech | API-based TTS            | gpt-4o-mini-tts  |
| Database       | Supabase                   | -                |
| Frontend       | HTML/CSS/JavaScript      | -                |
| Evaluation     | Custom WER (Levenshtein) | -                |

---

## Structured Data Collection

The system collects exactly these 7 attributes:

1. chief_complaint – Primary health concern
2. duration – How long symptoms have been present
3. severity – Pain/discomfort level (1–10 scale)
4. progression – Symptom trajectory (improving/worsening/stable)
5. associated_symptoms – Additional symptoms (list)
6. affected_body_part – Location of symptoms
7. onset_type – How symptoms started (sudden/gradual)

---

## Audio Requirements

### Supported Input Format

| Property    | Value      |
| ----------- | ---------- |
| Format      | WAV        |
| Encoding    | 16-bit PCM |
| Sample Rate | 16,000 Hz  |
| Channels    | Mono       |

Unsupported formats will return an error. The frontend automatically converts browser audio to the correct format.

---

## WER Evaluation (Optional)

1. Place 5 WAV audio files in `evaluation_samples/`

   * sample_1.wav through sample_5.wav
   * Must match format requirements (16kHz, 16-bit PCM, mono)
   * Must correspond to scripts defined in `evaluation.py`

2. Run:

```bash
python evaluation.py
```

Results will be saved to `evaluation_report.txt`.

---

## Project Structure

```
clinassist/
├── main.py
├── config.py
├── database.py
├── models.py
├── stt.py
├── tts.py
├── llm.py
├── risk.py
├── memory.py
├── intake.py
├── evaluation.py
├── static/
│   └── index.html
├── audio_output/
├── evaluation_samples/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## API Endpoints

### POST /session/new

Create a new intake session.

Response:

```json
{
  "session_id": "uuid",
  "message": "Session created successfully"
}
```

---

### POST /session/{session_id}/voice

Process voice audio input.

Response includes:

* transcript
* response_text
* audio_base64
* state
* is_complete
* risk_assessment
* latency_breakdown
* symptom_progress

---

### POST /session/{session_id}/text

Process text input (skip STT).

---

### GET /session/{session_id}/summary

Retrieve structured symptom record and risk assessment.

---

### GET /session/{session_id}/export

Export doctor-ready text summary.

---

### GET /health

Health check endpoint.

---

## Risk Categorization Rules

Deterministic rule-based logic only:

| Level    | Criteria                                    |
| -------- | ------------------------------------------- |
| CRITICAL | Severity ≥ 9 OR high-risk keywords detected |
| HIGH     | Severity ≥ 7 OR worsening + short duration  |
| MODERATE | Severity ≥ 4 OR ≥3 associated symptoms      |
| LOW      | All other cases                             |

Risk assessment is fully rule-based and does not involve LLM reasoning.

---

## Frontend Features

* Voice input (hold-to-record)
* Text fallback input
* Progress tracking for 7 structured attributes
* Color-coded risk badge
* Auto-play assistant audio
* Export session report
* Responsive layout

---

## Latency Tracking

The system logs:

* STT processing time
* LLM extraction and summary time
* TTS generation time
* Total end-to-end time

---

## Data Privacy

* All session data stored locally in SQLite
* No external database storage
* Audio files saved locally
* Session IDs use UUID format

---

## Development Constraints

* Non-streaming synchronous APIs
* Field immutability once captured
* Single clarification question per turn
* JSON parsing retry logic
* Structured error responses

---

## Academic Context

This capstone project demonstrates:

* Multi-modal AI integration
* Structured information extraction
* Finite state machine conversational design
* Deterministic risk stratification
* Performance measurement
* Responsible AI with explicit safety constraints

---

## License

Educational use only. Not for clinical deployment.

---

ClinAssist is a structured pre-screening support tool and does not provide medical diagnosis, treatment recommendations, or clinical decision support.

---
"# ClinAssist-Voice-enabled-AI-Medical-Assistant" 
"# ClinAssist-Voice-enabled-AI-Medical-Assistant" 
