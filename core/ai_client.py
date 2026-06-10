"""
JARVIS Universal AI Client
Plug in ANY API: OpenRouter, Groq, Anthropic, OpenAI, Gemini, Ollama, custom
Pure requests — no SDK packages required
"""
import requests
from typing import List, Dict


ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "openai":     "https://api.openai.com/v1/chat/completions",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "ollama":     "http://localhost:11434/api/chat",
    "custom":     "{base_url}",
}


class AIClient:
    def __init__(self, config):
        self.cfg     = config
        self.backend = config.get_backend()
        self.model   = config.get_model()
        self.api_key = config.get_api_key()

    def chat(self, messages: List[Dict], system_prompt: str = "") -> str:
        if not self.backend:
            return "No API key found. Please add one to your .env file."
        try:
            if self.backend == "anthropic": return self._anthropic(messages, system_prompt)
            if self.backend == "gemini":    return self._gemini(messages, system_prompt)
            if self.backend == "ollama":    return self._ollama(messages, system_prompt)
            return self._openai_compat(messages, system_prompt)
        except requests.Timeout:
            return "Request timed out. Try again."
        except requests.ConnectionError as e:
            return f"Connection error: {e}"
        except Exception as e:
            return f"AI error ({self.backend}): {e}"

    # ── OPENAI-COMPATIBLE (OpenRouter / Groq / OpenAI / custom) ──────────────

    def _openai_compat(self, messages, system_prompt):
        if self.backend == "custom" and self.cfg.custom_base_url:
            url = self.cfg.custom_base_url
        else:
            url = ENDPOINTS.get(self.backend, ENDPOINTS["openai"])

        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(self._flatten(messages))

        hdrs = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        if self.backend == "openrouter":
            hdrs["HTTP-Referer"] = "https://jarvis-local"
            hdrs["X-Title"]      = "JARVIS"

        body = {
            "model":       self.model,
            "messages":    msgs,
            "max_tokens":  self.cfg.max_tokens,
            "temperature": 0.85,
            "top_p":       0.9,
        }
        r = requests.post(url, json=body, headers=hdrs, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    # ── ANTHROPIC ─────────────────────────────────────────────────────────────

    def _anthropic(self, messages, system_prompt):
        hdrs = {
            "x-api-key":         self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type":      "application/json",
        }
        body = {
            "model":      self.model,
            "max_tokens": self.cfg.max_tokens,
            "temperature": 0.85,
            "messages":   self._flatten(messages),
        }
        if system_prompt:
            body["system"] = system_prompt
        r = requests.post("https://api.anthropic.com/v1/messages",
                          json=body, headers=hdrs, timeout=60)
        r.raise_for_status()
        blocks = r.json().get("content", [])
        return " ".join(b.get("text","") for b in blocks if b.get("type")=="text")

    # ── GEMINI ────────────────────────────────────────────────────────────────

    def _gemini(self, messages, system_prompt):
        url = ENDPOINTS["gemini"].format(model=self.model) + f"?key={self.api_key}"
        contents = []
        if system_prompt:
            contents += [
                {"role":"user",  "parts":[{"text":f"[SYSTEM] {system_prompt}"}]},
                {"role":"model", "parts":[{"text":"Understood."}]},
            ]
        for m in self._flatten(messages):
            role = "model" if m["role"]=="assistant" else "user"
            contents.append({"role":role,"parts":[{"text":m["content"]}]})
        body = {"contents": contents,
                "generationConfig":{"temperature":0.85,"maxOutputTokens":self.cfg.max_tokens}}
        r = requests.post(url, json=body, timeout=60)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    # ── OLLAMA ────────────────────────────────────────────────────────────────

    def _ollama(self, messages, system_prompt):
        url  = self.cfg.custom_base_url or "http://localhost:11434/api/chat"
        msgs = []
        if system_prompt:
            msgs.append({"role":"system","content":system_prompt})
        msgs.extend(self._flatten(messages))
        body = {"model":self.model,"messages":msgs,"stream":False,
                "options":{"temperature":0.85}}
        r = requests.post(url, json=body, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    # ── HELPER ────────────────────────────────────────────────────────────────

    def _flatten(self, messages):
        """Ensure all content is plain string"""
        out = []
        for m in messages:
            c = m.get("content","")
            if isinstance(c, list):
                c = "\n".join(x.get("content","") if isinstance(x,dict) else str(x) for x in c)
            out.append({"role": m["role"], "content": str(c)})
        return out

    def info(self) -> str:
        return f"{self.backend.upper()} / {self.model}"
