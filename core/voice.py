"""
JARVIS Voice v4 — fast, clean, interruptible
TTS: ElevenLabs (streaming) → gTTS → pyttsx3 → system
STT: Google Speech (full sentence, 0.8s pause threshold)
Stop: instant kill when user says stop phrase
"""
import os, re, threading, platform, subprocess, tempfile, time
from typing import Optional


class VoiceSystem:
    def __init__(self, config):
        self.config  = config
        self.system  = platform.system()
        self.tts_engine = None
        self.microphone_available = False
        self._stop  = threading.Event()
        self._lock  = threading.Lock()
        self._proc  = None   # current ffplay/mpg123 process

        self._init_tts()
        self._init_stt()

    # ── INIT ──────────────────────────────────────────────────────────────────

    def _init_tts(self):
        if self.config.elevenlabs_api_key:
            self.tts_engine = "elevenlabs"
            print("[VOICE] ElevenLabs (Daniel, British male) ✓"); return
        if self.config.openai_api_key_tts:
            self.tts_engine = "openai"; print("[VOICE] OpenAI TTS (onyx) ✓"); return
        try:
            from gtts import gTTS; import pygame
            self.tts_engine = "gtts"; print("[VOICE] Google TTS ✓"); return
        except ImportError: pass
        try:
            import pyttsx3
            self.tts_engine = "pyttsx3"; print("[VOICE] pyttsx3 (offline) ✓"); return
        except ImportError: pass
        if self.system == "Darwin":   self.tts_engine = "say"
        elif self.system == "Linux":
            for c in ["espeak-ng","espeak"]:
                if subprocess.run(["which",c],capture_output=True).returncode==0:
                    self.tts_engine=c; break
        elif self.system == "Windows": self.tts_engine = "powershell"
        if self.tts_engine: print(f"[VOICE] {self.tts_engine} ✓")
        else: print("[VOICE] No TTS — add ELEVENLABS_API_KEY for voice")

    def _init_stt(self):
        try:
            import speech_recognition as sr
            self.sr  = sr
            self.rec = sr.Recognizer()
            self.rec.energy_threshold         = 300
            self.rec.dynamic_energy_threshold = True
            self.rec.pause_threshold          = 0.8   # 0.8s silence = done speaking
            self.rec.phrase_threshold         = 0.3
            with sr.Microphone() as s:
                self.rec.adjust_for_ambient_noise(s, duration=0.3)
            self.microphone_available = True
            print("[VOICE] Microphone ✓")
        except ImportError:
            print("[VOICE] No SpeechRecognition — pip install SpeechRecognition pyaudio")
        except Exception as e:
            print(f"[VOICE] Mic unavailable ({e}) — text mode")

    # ── PUBLIC ────────────────────────────────────────────────────────────────

    def speak(self, text: str):
        """Speak — blocks until done or stopped"""
        clean = self._clean(text)
        if not clean or not self.tts_engine or not self.config.voice_enabled:
            return
        self._stop.clear()
        t = threading.Thread(target=self._tts_worker, args=(clean,), daemon=True)
        t.start()
        t.join(timeout=60)

    def stop(self):
        """Kill speech immediately"""
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            try: p.terminate()
            except: pass

    def is_speaking(self): return not self._stop.is_set()

    def listen(self) -> Optional[str]:
        """Block until user finishes sentence. Returns text or None."""
        if not self.microphone_available: return None
        try:
            with self.sr.Microphone() as src:
                audio = self.rec.listen(src, timeout=8, phrase_time_limit=30)
            try:    text = self.rec.recognize_google(audio)
            except self.sr.UnknownValueError: return None
            except self.sr.RequestError:
                try:    text = self.rec.recognize_sphinx(audio)
                except: return None
            if not text: return None
            tl = text.lower()
            if any(p in tl for p in self.config.stop_phrases):
                self.stop()
                return "__STOP__"
            return text
        except Exception:
            return None

    # ── TTS WORKER ────────────────────────────────────────────────────────────

    def _tts_worker(self, text: str):
        with self._lock:
            if self._stop.is_set(): return
            try:
                if   self.tts_engine == "elevenlabs": self._eleven(text)
                elif self.tts_engine == "openai":     self._openai_tts(text)
                elif self.tts_engine == "gtts":       self._gtts(text)
                elif self.tts_engine == "pyttsx3":    self._pyttsx3(text)
                elif self.tts_engine == "say":
                    self._run(["say","-v","Daniel","-r","175",text])
                elif self.tts_engine in ("espeak-ng","espeak"):
                    self._run([self.tts_engine,"-v","en-gb","-s","165","-p","30",text])
                elif self.tts_engine == "powershell":
                    ps = f'Add-Type -AssemblyName System.speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Rate=3;$s.Speak("{text}")'
                    self._run(["powershell","-command",ps])
            except Exception: pass

    def _eleven(self, text):
        import requests
        url  = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}/stream"
        r = requests.post(url,
            json={"text":text,"model_id":"eleven_turbo_v2_5",
                  "voice_settings":{"stability":0.4,"similarity_boost":0.8,
                                    "style":0.2,"use_speaker_boost":True}},
            headers={"xi-api-key":self.config.elevenlabs_api_key,
                     "Content-Type":"application/json","Accept":"audio/mpeg"},
            timeout=15, stream=True)
        if r.status_code != 200:
            print(f"[VOICE] ElevenLabs {r.status_code}"); self._gtts(text); return
        with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f:
            for chunk in r.iter_content(4096):
                if self._stop.is_set(): break
                f.write(chunk)
            fname = f.name
        if not self._stop.is_set(): self._play(fname)
        try: os.unlink(fname)
        except: pass

    def _openai_tts(self, text):
        import requests
        r = requests.post("https://api.openai.com/v1/audio/speech",
            json={"model":"tts-1","input":text,"voice":self.config.openai_tts_voice},
            headers={"Authorization":f"Bearer {self.config.openai_api_key_tts}",
                     "Content-Type":"application/json"},
            timeout=15)
        if r.status_code != 200: self._gtts(text); return
        with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f:
            f.write(r.content); fname=f.name
        self._play(fname)
        try: os.unlink(fname)
        except: pass

    def _gtts(self, text):
        try:
            from gtts import gTTS; import io
            buf = io.BytesIO()
            gTTS(text=text,lang='en',tld='co.uk').write_to_fp(buf)
            with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f:
                f.write(buf.getvalue()); fname=f.name
            self._play(fname)
            try: os.unlink(fname)
            except: pass
        except Exception: self._pyttsx3(text)

    def _pyttsx3(self, text):
        try:
            import pyttsx3; e=pyttsx3.init()
            e.setProperty('rate',170); e.setProperty('volume',0.95)
            for v in e.getProperty('voices') or []:
                if any(x in v.name.lower() for x in ['david','daniel','mark']):
                    e.setProperty('voice',v.id); break
            e.say(text); e.runAndWait()
        except Exception: pass

    def _play(self, path):
        """Play file — tries pygame first (fastest), then ffplay"""
        if self._stop.is_set(): return
        # pygame
        try:
            import pygame
            if not pygame.mixer.get_init(): pygame.mixer.init(frequency=44100)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop.is_set(): pygame.mixer.music.stop(); return
                pygame.time.wait(30)
            return
        except Exception: pass
        # ffplay
        try:
            self._proc = subprocess.Popen(
                ["ffplay","-nodisp","-autoexit","-loglevel","quiet",path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while self._proc.poll() is None:
                if self._stop.is_set(): self._proc.terminate(); return
                time.sleep(0.03)
            return
        except FileNotFoundError: pass
        # mpg123
        try:
            self._proc = subprocess.Popen(["mpg123","-q",path],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            while self._proc.poll() is None:
                if self._stop.is_set(): self._proc.terminate(); return
                time.sleep(0.03)
        except FileNotFoundError: pass

    def _run(self, cmd):
        self._proc = subprocess.Popen(cmd,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        while self._proc.poll() is None:
            if self._stop.is_set(): self._proc.terminate(); return
            time.sleep(0.03)

    # ── CLEAN TEXT ────────────────────────────────────────────────────────────

    def _clean(self, text):
        text = re.sub(r'<tool>.*?</tool>','',text,flags=re.DOTALL)
        text = re.sub(r'\*\*(.+?)\*\*',r'\1',text)
        text = re.sub(r'\*(.+?)\*',r'\1',text)
        text = re.sub(r'`{1,3}[\s\S]*?`{1,3}','[code]',text)
        text = re.sub(r'^#{1,6}\s+','',text,flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*•]\s+','',text,flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)',r'\1',text)
        text = re.sub(r'\n+',' ',text)
        text = re.sub(r'\s+',' ',text).strip()
        # Hard cap: speak max 300 chars for speed
        if len(text) > 300:
            parts = re.split(r'(?<=[.!?])\s+',text)
            out = ""
            for p in parts:
                if len(out)+len(p) < 280: out += p+" "
                else: break
            text = out.strip() or text[:280]
        return text
