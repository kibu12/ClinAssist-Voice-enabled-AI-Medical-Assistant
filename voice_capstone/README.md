# ClinAssist - Speech-Driven Structured Clinical Intake System

> **Academic Capstone Project**

ClinAssist is a structured pre-screening support tool that collects symptom information through voice or text interaction. **This system does not provide medical diagnosis or treatment advice and does not replace a physician.**

## 🎯 Overview

ClinAssist uses AI-powered speech recognition and natural language processing to collect structured symptom data through conversational interaction. The system:

- Collects 7 structured symptom attributes via voice or text
- Uses deterministic rule-based risk categorization (NO AI diagnosis)
- Generates clinical-style summaries for healthcare providers
- Tracks latency metrics for STT, LLM, and TTS operations
- Includes ASR evaluation using Word Error Rate (WER)

## 🚨 Safety & Scope Limitations

**This system does NOT:**
- Perform medical diagnosis
- Provide treatment advice
- Suggest medication
- Predict diseases
- Use LLM for risk assessment (uses deterministic rules only)

**This is an academic demonstration project for structured data collection only.**

## 🛠️ Tech Stack

| Component | Technology | Model |
|-----------|-----------|-------|
| Backend | Python 3.11+, FastAPI | - |
| Speech-to-Text | Nexus API | whisper-1 |
| LLM | Nexus API | gemini-2.5-flash |
| Text-to-Speech | Nexus API | gpt-4o-mini-tts |
| Database | SQLite | - |
| Frontend | HTML/CSS/JavaScript | - |
| Evaluation | Custom WER (Levenshtein) | - |

## 📋 Structured Data Collection

The system collects exactly these 7 attributes:

1. **chief_complaint** - Primary health concern
2. **duration** - How long symptoms have been present
3. **severity** - Pain/discomfort level (1-10 scale)
4. **progression** - Symptom trajectory (improving/worsening/stable)
5. **associated_symptoms** - Additional symptoms (list)
6. **affected_body_part** - Location of symptoms
7. **onset_type** - How symptoms started (sudden/gradual)

## 🎵 Audio Requirements

### Supported Input Format

| Property | Value |
|----------|-------|
| Format | WAV |
| Encoding | 16-bit PCM |
| Sample Rate | 16,000 Hz |
| Channels | Mono |

**Unsupported formats will return an error.** The frontend automatically converts browser audio to the correct format.

## 🚀 Setup Instructions

### 1. Clone or Download Project

```bash
cd "c:\Users\dell_\OneDrive\Desktop\voice AI capstone"
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
NEXUS_API_KEY=your_nexus_api_key_here
NEXUS_BASE_URL=https://your-nexus-endpoint-url
```

**Important:** Never commit the `.env` file to version control. Use `.env.example` as a template.

### 4. Run the Application

```bash
uvicorn main:app --reload
```

The API will be available at: `http://localhost:8000`
The frontend UI will be at: `http://localhost:8000/static/index.html`

### 5. Run WER Evaluation (Optional)

First, place 5 WAV audio files in `evaluation_samples/`:
- `sample_1.wav` through `sample_5.wav`
- Must match the format requirements (16kHz, 16-bit PCM, mono)
- Should correspond to the 5 sample scripts defined in `evaluation.py`

Then run:

```bash
python evaluation.py
```

Results will be saved to `evaluation_report.txt`

## 📁 Project Structure

```
clinassist/
├── main.py                 # FastAPI application with all endpoints
├── config.py              # Configuration and environment variables
├── database.py            # SQLite database layer (CRUD operations)
├── models.py              # Pydantic models and schemas
├── stt.py                 # Speech-to-Text (whisper-1 via Nexus)
├── tts.py                 # Text-to-Speech (gpt-4o-mini-tts via Nexus)
├── llm.py                 # LLM integration (gemini-2.5-flash via Nexus)
├── risk.py                # Deterministic risk categorization
├── memory.py              # Session memory and state management
├── intake.py              # Intake state machine (FSM)
├── evaluation.py          # WER evaluation module
├── static/
│   └── index.html         # Minimalist frontend UI
├── audio_output/          # Generated TTS audio files
├── evaluation_samples/    # Sample audio for WER testing
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

## 🔌 API Endpoints

### `POST /session/new`
Create a new intake session.

**Response:**
```json
{
  "session_id": "uuid",
  "message": "Session created successfully"
}
```

### `POST /session/{session_id}/voice`
Process voice audio input.

**Request:** Multipart form with audio file (WAV format)

**Response:**
```json
{
  "transcript": "transcribed text",
  "response_text": "assistant response",
  "audio_base64": "base64 encoded audio",
  "state": "collecting",
  "is_complete": false,
  "risk_assessment": null,
  "latency_breakdown": {
    "stt_ms": 245.3,
    "llm_ms": 892.1,
    "tts_ms": 456.7,
    "total_ms": 1594.1
  },
  "symptom_progress": {
    "chief_complaint": true,
    "duration": false,
    ...
  }
}
```

### `POST /session/{session_id}/text`
Process text input (skip STT).

**Request:**
```json
{
  "text": "user message"
}
```

**Response:** Same as `/voice` endpoint

### `GET /session/{session_id}/summary`
Retrieve session summary with symptom data and risk assessment.

**Response:**
```json
{
  "session_id": "uuid",
  "symptom_record": { ... },
  "risk_assessment": { ... },
  "summary": "clinical summary text",
  "state": "complete"
}
```

### `GET /session/{session_id}/export`
Export session in doctor-ready text format.

**Response:** Plain text report with conversation transcript, structured data, risk assessment, and clinical summary.

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-03T12:00:00"
}
```

## 🧮 Risk Categorization Rules

**Deterministic (rule-based only, NO LLM involvement):**

| Level | Criteria |
|-------|----------|
| **CRITICAL** | Severity ≥ 9 OR chief complaint contains: "chest pain", "difficulty breathing", "loss of consciousness", "stroke", "seizure", "severe bleeding" |
| **HIGH** | Severity ≥ 7 OR (progression = "worsening" AND duration ≤ 2 days) |
| **MODERATE** | Severity ≥ 4 OR associated symptoms count ≥ 3 |
| **LOW** | All other cases |

## 🎨 Frontend Features

- **Minimalist Design:** Clean, spacious layout with soft colors and smooth animations
- **Voice Input:** Hold-to-record microphone button with recording indicator
- **Text Fallback:** Type messages if voice input unavailable
- **Progress Tracking:** 7 dots indicating completion of each symptom attribute
- **Risk Display:** Color-coded badge (green/yellow/orange/red) with recommendations
- **Auto-play Audio:** Assistant responses played automatically
- **Export Function:** Download complete session report
- **Responsive:** Works on desktop and mobile devices

## 📊 Latency Tracking

All operations are logged to the `latency_logs` table:

- **STT** - Speech-to-text transcription time
- **LLM** - Language model processing time (extraction, clarification, summary)
- **TTS** - Text-to-speech generation time
- **Total** - End-to-end request time

## 🧪 WER Evaluation

The system includes Word Error Rate evaluation for ASR accuracy:

1. Define ground truth scripts in `evaluation.py`
2. Place corresponding WAV files in `evaluation_samples/`
3. Run: `python evaluation.py`
4. Review results in `evaluation_report.txt`

**Formula:** WER = (Substitutions + Deletions + Insertions) / Reference Word Count

## 🔧 Troubleshooting

### API Key Errors
- Ensure `.env` file exists in project root
- Verify `NEXUS_API_KEY` and `NEXUS_BASE_URL` are set correctly
- Check API key has access to whisper-1, gemini-2.5-flash, and gpt-4o-mini-tts

### Audio Format Errors
- Verify audio is WAV format (16kHz, 16-bit PCM, mono)
- Frontend automatically converts, but manual uploads must match format
- Use audio conversion tools if needed: `ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 output.wav`

### Database Errors
- Delete `clinassist.db` to reset database
- Restart application to reinitialize tables

### Import Errors
- Run `pip install -r requirements.txt` to install all dependencies
- Use Python 3.11 or higher

### Microphone Access
- Allow browser permissions for microphone
- Use HTTPS in production (HTTP works for localhost)

## 🔒 Data Privacy

- All data stored locally in SQLite database
- No cloud storage or external data transmission (except Nexus API for processing)
- Audio files saved to local `audio_output/` directory
- Session IDs are UUIDs (not personally identifiable)

## 📝 Development Notes

- **No Streaming:** All APIs are synchronous request-response
- **Field Immutability:** Once a symptom field is filled, it cannot be overwritten
- **Single Question Policy:** Only one clarification question asked at a time
- **Retry Logic:** JSON parsing failures retry up to 2 times
- **Error Handling:** All errors return structured JSON with error and detail fields

## 📚 Academic Context

This is a scope-controlled capstone project demonstrating:
- Multi-modal AI integration (speech, text, LLM)
- Structured data extraction from natural conversation
- State machine design for conversational flow
- Deterministic risk stratification
- Performance measurement and evaluation
- Responsible AI with explicit safety constraints

## 🤝 Contributing

This is an academic capstone project. Not accepting external contributions.

## 📄 License

Educational use only. Not for clinical deployment.

## 🔗 Support

For issues with Nexus API, contact your API provider.
For project issues, refer to troubleshooting section above.

---

**Remember:** ClinAssist is a demonstration tool for structured symptom collection and does not provide medical diagnosis, treatment recommendations, or clinical decision support.
