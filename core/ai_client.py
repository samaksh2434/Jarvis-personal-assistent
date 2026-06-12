"""
JARVIS AI Client v4 — multi-API fallback, fast, no bloat
Priority: Groq → OpenRouter → Gemini → OpenAI → Anthropic → Ollama
Skips dead APIs instantly, retries rate-limited ones once after short wait.
"""
import time, requests
from typing import List, Dict

ENDPOINTS = {
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai":     "https://api.openai.com/v1/chat/completions",
    "anthropic":  "https://api.anthropic.com/v1/messages",
}
SKIP  = {401, 403, 404}   # bad key / not found — skip forever
RETRY = {429, 500, 503}   # temporary — wait briefly, try once more


class AIClient:
    def __init__(self, config):
        self.cfg    = config
        self.chain  = config.get_api_chain()
        self._dead  = set()   # indices of permanently broken backends
        self._cur   = 0       # index of currently active backend
        names = [b for b,k,m in self.chain]
        print(f"[AI] API chain: {' → '.join(names)}")

    def chat(self, messages: List[Dict], system: str = "") -> str:
        """Call AI. Auto-falls to next backend on any failure."""
        indices = list(range(self._cur, len(self.chain))) + \
                  list(range(0, self._cur))

        for i in indices:
            if i in self._dead:
                continue
            backend, key, model = self.chain[i]
            try:
                result = self._dispatch(backend, key, model, messages, system)
                if i != self._cur:
                    print(f"[AI] Using {backend.upper()} / {model}")
                    self._cur = i
                return result

            except _Skip as e:
                print(f"[AI] {backend.upper()} dead ({e}) — skipping forever")
                self._dead.add(i)

            except _RateLimit as e:
                wait = min(e.wait, 8)   # cap wait at 8s for speed
                print(f"[AI] {backend.upper()} rate limit — waiting {wait}s")
                time.sleep(wait)
                try:
                    result = self._dispatch(backend, key, model, messages, system)
                    self._cur = i
                    return result
                except Exception:
                    self._dead.add(i)   # still failing → skip

            except Exception as e:
                print(f"[AI] {backend.upper()} error: {e}")
                # Don't permanently kill — could be transient network issue
                continue

        # All APIs tried — reset dead set and try Ollama
        self._dead.clear()
        backend, key, model = self.chain[-1]  # Ollama is always last
        try:
            return self._dispatch(backend, key, model, messages, system)
        except Exception as e:
            return f"All backends failed. Last: {e}"

    # ── DISPATCH ──────────────────────────────────────────────────────────────

    def _dispatch(self, backend, key, model, messages, system):
        if   backend == "anthropic": return self._anthropic(key, model, messages, system)
        elif backend == "gemini":    return self._gemini(key, model, messages, system)
        elif backend == "ollama":    return self._ollama(model, messages, system)
        else:                        return self._oai(backend, key, model, messages, system)

    # ── OPENAI-COMPATIBLE ─────────────────────────────────────────────────────

    def _oai(self, backend, key, model, messages, system):
        url  = self.cfg.custom_base_url if backend == "custom" else ENDPOINTS[backend]
        hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if backend == "openrouter":
            hdrs["HTTP-Referer"] = "https://jarvis"
            hdrs["X-Title"]      = "JARVIS"
        msgs = ([{"role":"system","content":system}] if system else []) + self._flat(messages)
        body = {"model":model,"messages":msgs,
                "max_tokens":self.cfg.max_tokens,"temperature":0.7}
        r = requests.post(url, json=body, headers=hdrs,
                          timeout=self.cfg.api_timeout)
        self._raise(r)
        return r.json()["choices"][0]["message"]["content"].strip()

    # ── ANTHROPIC ─────────────────────────────────────────────────────────────

    def _anthropic(self, key, model, messages, system):
        hdrs = {"x-api-key":key,"anthropic-version":"2023-06-01",
                "Content-Type":"application/json"}
        body = {"model":model,"max_tokens":self.cfg.max_tokens,
                "temperature":0.7,"messages":self._flat(messages)}
        if system: body["system"] = system
        r = requests.post(ENDPOINTS["anthropic"], json=body, headers=hdrs,
                          timeout=self.cfg.api_timeout)
        self._raise(r)
        return " ".join(b["text"] for b in r.json().get("content",[])
                        if b.get("type")=="text").strip()

    # ── GEMINI ────────────────────────────────────────────────────────────────

    def _gemini(self, key, model, messages, system):
        # Key goes ONLY in URL param — no auth header needed
        url = (f"https://generativelanguage.googleapis.com/v1beta/models"
               f"/{model}:generateContent?key={key}")
        contents = []
        if system:
            contents += [{"role":"user","parts":[{"text":f"[SYSTEM] {system}"}]},
                         {"role":"model","parts":[{"text":"Understood."}]}]
        for m in self._flat(messages):
            role = "model" if m["role"]=="assistant" else "user"
            contents.append({"role":role,"parts":[{"text":m["content"]}]})
        body = {"contents":contents,
                "generationConfig":{"temperature":0.7,
                                    "maxOutputTokens":self.cfg.max_tokens}}
        r = requests.post(url, json=body,
                          headers={"Content-Type":"application/json"},
                          timeout=self.cfg.api_timeout)
        self._raise(r)
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError,IndexError):
            raise _Skip(f"Bad response: {r.text[:80]}")

    # ── OLLAMA ────────────────────────────────────────────────────────────────

    def _ollama(self, model, messages, system):
        url  = self.cfg.ollama_url.rstrip("/") + "/api/chat"
        msgs = ([{"role":"system","content":system}] if system else []) + self._flat(messages)
        body = {"model":model,"messages":msgs,"stream":False,
                "options":{"temperature":0.7,"num_predict":self.cfg.max_tokens}}
        try:
            r = requests.post(url, json=body, timeout=self.cfg.api_timeout)

        except requests.ConnectionError:
            raise _Skip("Ollama not running — start with: ollama serve")
        self._raise(r)
        return r.json()["message"]["content"].strip()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _raise(self, r):
        if r.status_code == 200: return
        c = r.status_code
        try:    msg = str(r.json().get("error",r.text))[:100]
        except: msg = r.text[:100]
        if c in SKIP:  raise _Skip(f"{c} {msg}")
        if c in RETRY:
            wait = 5
            try: wait = min(int(r.headers.get("Retry-After","5")), 15)
            except: pass
            raise _RateLimit(f"{c} {msg}", wait)
        raise _Skip(f"{c} {msg}")

    def _flat(self, msgs):
        out = []
        for m in msgs:
            c = m.get("content","")
            if isinstance(c, list):
                c = " ".join(x.get("content","") if isinstance(x,dict) else str(x) for x in c)
            role = m.get("role","user")
            if out and out[-1]["role"] == role:
                out[-1]["content"] += " " + str(c)
            else:
                out.append({"role":role,"content":str(c)})
        return out

    def info(self):
        b,k,m = self.chain[self._cur]
        return f"{b.upper()} / {m}"

class _Skip(Exception): pass
class _RateLimit(Exception):
    def __init__(self, msg, wait=5): super().__init__(msg); self.wait=wait
