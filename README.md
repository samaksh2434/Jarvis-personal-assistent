# J.A.R.V.I.S — v2.0

> *"Just A Rather Very Intelligent System"*
> Human-like male voice · Listens to full sentences · Stops on command · Any AI API

---

## Quick Start

```bash
# 1. Install dependencies
bash setup.sh
# or manually:
pip install requests python-dotenv SpeechRecognition PyAudio pygame gTTS pyttsx3 mss psutil duckduckgo-search pyperclip

# 2. Keys are already in .env — just run:
python3 jarvis.py
```

---

## Voice

**JARVIS uses ElevenLabs "Daniel"** — a British male neural voice, calm and authoritative.
- Your ElevenLabs key is pre-configured in `.env`
- Free tier = 10,000 characters/month (~30 min of speech)
- If ElevenLabs quota runs out, falls back to Google TTS (British accent)

---

## AI Model

**Uses OpenRouter** — routes to the best free model (Llama 3.3 70B by default).
- Your OpenRouter key is pre-configured in `.env`
- To switch models, set `AI_MODEL=` in `.env`

**Free models on OpenRouter you can use:**
```
meta-llama/llama-3.3-70b-instruct:free    ← default (best)
mistralai/mistral-7b-instruct:free
google/gemma-2-9b-it:free
microsoft/phi-3-medium-128k-instruct:free
```

---

## Using ANY AI API

Edit `.env` — just swap the key and optionally set a model:

```env
# Groq (free, very fast)
GROQ_API_KEY=your_key

# Anthropic Claude
ANTHROPIC_API_KEY=your_key

# OpenAI
OPENAI_API_KEY=your_key

# Gemini
GEMINI_API_KEY=your_key

# Local Ollama (no key needed)
# Set backend to custom in config, point to localhost

# Force a specific model
AI_MODEL=gpt-4o-mini
```

---

## Stop JARVIS Mid-Speech

Say any of these while JARVIS is talking:
- **"Jarvis stop"**
- **"Jarvis shut up"**
- **"Stop talking"**
- **"Enough"**
- **"Shut up"**

JARVIS will stop immediately.

---

## Listening Behaviour

JARVIS waits for your **complete sentence** before responding.
It detects end-of-speech by silence (1 second pause).
No need to press Enter or say a trigger word — just speak naturally.

---

## Example Commands

```
"Open YouTube in Chrome"
"What's on my screen right now?"
"Create a Python script that backs up my Documents folder"
"Find all PDF files in my Downloads"
"What's using the most CPU?"
"Search the web for the latest news on AI"
"Write a todo list and save it to my Desktop"
"Edit my config.py and change debug to false"
"How much disk space do I have left?"
"I'm bored — tell me something interesting"
```

---

## Files

```
jarvis/
├── jarvis.py           ← run this
├── .env                ← your API keys
├── requirements.txt
├── setup.sh
└── core/
    ├── config.py       ← all settings
    ├── assistant.py    ← brain + conversation loop
    ├── ai_client.py    ← universal AI API client
    ├── voice.py        ← ElevenLabs TTS + mic input
    ├── executor.py     ← file/command/system tools
    └── screen.py       ← screen capture
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No voice output | Install pygame: `pip install pygame` |
| Mic not working | `pip install PyAudio` or `sudo apt install python3-pyaudio` |
| ElevenLabs 401 | Check your API key in `.env` |
| OpenRouter error | Check key, or try a different free model |
| "ffplay not found" | `sudo apt install ffmpeg` (Linux) or `brew install ffmpeg` (Mac) |
