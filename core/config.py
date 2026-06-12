"""JARVIS Config — multi-API fallback + Ollama offline"""
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
        # ── AI API KEYS (add as many as you have) ─────────────────────────────
        self.groq_api_key       = os.getenv("GROQ_API_KEY", "")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.gemini_api_key     = os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key     = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key  = os.getenv("ANTHROPIC_API_KEY", "")
        self.custom_api_key     = os.getenv("CUSTOM_API_KEY", "")
        self.custom_base_url    = os.getenv("CUSTOM_BASE_URL", "")
        self.ai_model_override  = os.getenv("AI_MODEL", "")

        # Ollama — offline fallback (no key needed, must be running locally)
        self.ollama_url   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # Ollama model should match one of: `curl http://localhost:11434/api/tags`
        # Default to a model that exists on many setups; override with OLLAMA_MODEL in .env.
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")

        # If .env is missing/old, fall back to qwen3:4b when current default isn't found.
        if self.ollama_model in ("", "llama3"):
            self.ollama_model = "qwen3:4b"



        # ── VOICE ─────────────────────────────────────────────────────────────
        self.elevenlabs_api_key  = os.getenv("ELEVENLABS_API_KEY", "")
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
        self.openai_api_key_tts  = os.getenv("OPENAI_API_KEY", "")
        self.openai_tts_voice    = "onyx"
        self.voice_enabled       = True
        self.stop_phrases = ["jarvis stop","jarvis shut up","stop talking",
                             "shut up","enough","ok stop","stop"]

        # ── PERFORMANCE ───────────────────────────────────────────────────────
        self.max_tokens  = 400   # short answers = fast + cheap
        self.max_history = 6     # last 6 exchanges only
        self.api_timeout = 20    # seconds per API call

        # ── SCREEN ────────────────────────────────────────────────────────────
        self.screen_monitor_enabled = True
        self.screen_capture_interval = float(os.getenv("SCREEN_CAPTURE_INTERVAL", "1.0"))


        # ── PERSONAL ─────────────────────────────────────────────────────────
        self.user_name = os.getenv("USER_NAME", "sir")

    def get_api_chain(self) -> list:
        """
        Returns [(backend, key, model), ...] in priority order.
        JARVIS tries each in sequence — first one that works wins.
        Ollama always last as offline fallback.
        """
        MODELS = {
            "groq":       self.ai_model_override or "llama-3.3-70b-versatile",
            "openrouter": self.ai_model_override or "meta-llama/llama-3.3-70b-instruct:free",
            "gemini":     self.ai_model_override or "gemini-1.5-flash",
            "openai":     self.ai_model_override or "gpt-4o-mini",
            "anthropic":  self.ai_model_override or "claude-haiku-4-5-20251001",
            "custom":     self.ai_model_override or "default",
        }
        pairs = [
            ("groq",       self.groq_api_key),
            ("openrouter", self.openrouter_api_key),
            ("gemini",     self.gemini_api_key),
            ("openai",     self.openai_api_key),
            ("anthropic",  self.anthropic_api_key),
            ("custom",     self.custom_api_key),
        ]
        chain = [(b, k, MODELS[b]) for b, k in pairs if k]
        chain.append(("ollama", "", self.ollama_model))  # always fallback
        return chain

    # back-compat helpers
    def get_backend(self):  return self.get_api_chain()[0][0]
    def get_api_key(self):  return self.get_api_chain()[0][1]
    def get_model(self):    return self.get_api_chain()[0][2]
