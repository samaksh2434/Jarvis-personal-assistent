"""JARVIS — Configuration (auto-detects whichever API key is set)"""
import os
from pathlib import Path

def _load_env():
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

class Config:
    def __init__(self):
        # ── API KEYS ──────────────────────────────────────────────────────────
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.groq_api_key       = os.getenv("GROQ_API_KEY", "")
        self.anthropic_api_key  = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_api_key     = os.getenv("OPENAI_API_KEY", "")
        self.gemini_api_key     = os.getenv("GEMINI_API_KEY", "")
        self.custom_api_key     = os.getenv("CUSTOM_API_KEY", "")
        self.custom_base_url    = os.getenv("CUSTOM_BASE_URL", "")   # e.g. Ollama
        self.ai_model_override  = os.getenv("AI_MODEL", "")          # force specific model

        # ── ELEVENLABS VOICE ──────────────────────────────────────────────────
        self.elevenlabs_api_key  = os.getenv("ELEVENLABS_API_KEY", "")
        # Daniel = British calm male — best JARVIS match
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
        self.elevenlabs_model    = "eleven_turbo_v2_5"   # fastest + highest quality
        self.openai_tts_voice    = "onyx"                # deep male (if using OpenAI TTS)

        # ── VOICE BEHAVIOUR ───────────────────────────────────────────────────
        self.voice_enabled = True
        self.stop_phrases  = [               # user says these → JARVIS stops mid-speech
            "jarvis shut up", "jarvis stop", "stop talking", "shut up",
            "enough", "jarvis quiet", "ok stop", "stop"
        ]

        # ── SCREEN ────────────────────────────────────────────────────────────
        self.screen_monitor_enabled  = True
        self.screen_capture_interval = 5

        # ── CONVERSATION ──────────────────────────────────────────────────────
        self.max_tokens  = 2048
        self.max_history = 30

        # ── PERSONAL ─────────────────────────────────────────────────────────
        self.user_name = os.getenv("USER_NAME", "sir")

    # ── BACKEND AUTO-DETECTION ───────────────────────────────────────────────

    def get_backend(self) -> str:
        if self.openrouter_api_key: return "openrouter"
        if self.groq_api_key:       return "groq"
        if self.anthropic_api_key:  return "anthropic"
        if self.openai_api_key:     return "openai"
        if self.gemini_api_key:     return "gemini"
        if self.custom_api_key:     return "custom"
        return ""

    def get_api_key(self) -> str:
        b = self.get_backend()
        return {
            "openrouter": self.openrouter_api_key,
            "groq":       self.groq_api_key,
            "anthropic":  self.anthropic_api_key,
            "openai":     self.openai_api_key,
            "gemini":     self.gemini_api_key,
            "custom":     self.custom_api_key,
        }.get(b, "")

    def get_model(self) -> str:
        if self.ai_model_override:
            return self.ai_model_override
        return {
            "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
            "groq":       "llama-3.3-70b-versatile",
            "anthropic":  "claude-sonnet-4-20250514",
            "openai":     "gpt-4o-mini",
            "gemini":     "gemini-2.5-flash",

            "custom":     "default",
        }.get(self.get_backend(), "llama-3.3-70b-versatile")
