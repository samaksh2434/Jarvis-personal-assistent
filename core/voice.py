"""
JARVIS Voice System
- ElevenLabs for human-like male voice (Daniel, British)
- Listens to FULL sentence before responding
- Stops instantly when user says "jarvis stop" / "jarvis shut up"
- Falls back: OpenAI TTS → gTTS → pyttsx3 → system
"""

import os, re, threading, platform, subprocess, tempfile, time
from typing import Optional


class VoiceSystem:
    def __init__(self, config):
        self.config   = config
        self.system   = platform.system()
        self.tts_engine = None
        self.microphone_available = False
        self._speaking    = False          # True while audio is playing
        self._stop_event  = threading.Event()   # set this to kill audio mid-play
        self._tts_lock    = threading.Lock()
        self._stop_listener_active = False

        self._init_tts()
        self._init_stt()

    # ── INIT ──────────────────────────────────────────────────────────────────

    def _init_tts(self):
        if self.config.elevenlabs_api_key:
            self.tts_engine = "elevenlabs"
            print("[VOICE] TTS: ElevenLabs — Daniel (British male, neural) ✓")
            return
        if self.config.openai_api_key:
            self.tts_engine = "openai_tts"
            print("[VOICE] TTS: OpenAI TTS (onyx — deep male) ✓")
            return
        try:
            from gtts import gTTS; import pygame
            self.tts_engine = "gtts"
            print("[VOICE] TTS: Google TTS (British) ✓")
            return
        except ImportError: pass
        try:
            import pyttsx3
            self.tts_engine = "pyttsx3"
            print("[VOICE] TTS: pyttsx3 (offline) ✓")
            return
        except ImportError: pass
        if self.system == "Darwin":
            self.tts_engine = "say"; print("[VOICE] TTS: macOS say ✓")
        elif self.system == "Linux":
            for c in ["espeak-ng","espeak"]:
                if subprocess.run(["which",c],capture_output=True).returncode==0:
                    self.tts_engine = c; print(f"[VOICE] TTS: {c} ✓"); return
        elif self.system == "Windows":
            self.tts_engine = "powershell"; print("[VOICE] TTS: Windows SAPI ✓")

    def _init_stt(self):
        try:
            import speech_recognition as sr
            self.sr = sr
            self.rec = sr.Recognizer()
            self.rec.energy_threshold        = 300
            self.rec.dynamic_energy_threshold = True
            self.rec.pause_threshold          = 1.0   # wait 1s silence = end of sentence
            self.rec.phrase_threshold         = 0.3
            with sr.Microphone() as src:
                self.rec.adjust_for_ambient_noise(src, duration=0.5)
            self.microphone_available = True
            print("[VOICE] Microphone ✓  (listening for full sentences)")
        except ImportError:
            print("[VOICE] SpeechRecognition not installed → text input mode")
            print("        pip install SpeechRecognition pyaudio")
        except Exception as e:
            print(f"[VOICE] Mic unavailable: {e} → text input mode")

    # ── PUBLIC: SPEAK ─────────────────────────────────────────────────────────

    def speak(self, text: str):
        """Speak text. Stops if user triggers stop phrase."""
        clean = self._clean(text)
        if not clean or not self.tts_engine or not self.config.voice_enabled:
            return
        self._stop_event.clear()
        self._speaking = True
        t = threading.Thread(target=self._speak_worker, args=(clean,), daemon=True)
        t.start()
        t.join(timeout=90)
        self._speaking = False

    def stop_speaking(self):
        """Interrupt TTS immediately"""
        self._stop_event.set()
        self._speaking = False

    def is_speaking(self) -> bool:
        return self._speaking

    # ── PUBLIC: LISTEN ────────────────────────────────────────────────────────

    def listen(self) -> Optional[str]:
        """
        Listen until user stops speaking (full sentence).
        Returns transcribed text or None.
        Also checks for stop phrases to kill active TTS.
        """
        if not self.microphone_available:
            return None
        try:
            with self.sr.Microphone() as src:
                # Adjust per call for noise robustness
                self.rec.adjust_for_ambient_noise(src, duration=0.2)
                # listen() blocks until pause_threshold silence detected → full sentence
                audio = self.rec.listen(src, timeout=8, phrase_time_limit=40)
            try:
                text = self.rec.recognize_google(audio)
            except self.sr.UnknownValueError:
                return None
            except self.sr.RequestError:
                try:   text = self.rec.recognize_sphinx(audio)
                except: return None

            if not text:
                return None

            # Check for stop command mid-speech
            if self._is_stop_phrase(text):
                self.stop_speaking()
                print("[JARVIS] Understood — stopping.")
                return "__STOP__"    # caller handles this

            return text
        except Exception:
            return None

    # ── INTERNAL: SPEAK WORKER ───────────────────────────────────────────────

    def _speak_worker(self, text: str):
        with self._tts_lock:
            if self._stop_event.is_set():
                return
            try:
                if   self.tts_engine == "elevenlabs": self._eleven(text)
                elif self.tts_engine == "openai_tts": self._openai_tts(text)
                elif self.tts_engine == "gtts":       self._gtts(text)
                elif self.tts_engine == "pyttsx3":    self._pyttsx3(text)
                elif self.tts_engine == "say":
                    self._run_proc(["say","-v","Daniel","-r","170",text])
                elif self.tts_engine in ("espeak-ng","espeak"):
                    self._run_proc([self.tts_engine,"-v","en-gb","-s","160","-p","30",text])
                elif self.tts_engine == "powershell":
                    ps = f'Add-Type -AssemblyName System.speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Rate=2;$s.Speak("{text}")'
                    self._run_proc(["powershell","-command",ps])
            except Exception:
                pass

    # ── TTS ENGINES ──────────────────────────────────────────────────────────

    def _eleven(self, text: str):
        """ElevenLabs — most human-like neural voice"""
        try:
            import requests
            url  = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}/stream"
            hdrs = {
                "xi-api-key":   self.config.elevenlabs_api_key,
                "Content-Type": "application/json",
                "Accept":       "audio/mpeg",
            }
            body = {
                "text":     text,
                "model_id": self.config.elevenlabs_model,
                "voice_settings": {
                    "stability":        0.45,   # more natural variation
                    "similarity_boost": 0.82,   # stays true to voice
                    "style":            0.30,   # expressive
                    "use_speaker_boost": True
                },
                "output_format": "mp3_44100_128",
            }
            r = requests.post(url, json=body, headers=hdrs, timeout=20, stream=True)
            if r.status_code == 200:
                # Stream to temp file then play
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    for chunk in r.iter_content(chunk_size=4096):
                        if self._stop_event.is_set(): break
                        f.write(chunk)
                    fname = f.name
                if not self._stop_event.is_set():
                    self._play_file(fname)
                try: os.unlink(fname)
                except: pass
            else:
                print(f"[VOICE] ElevenLabs {r.status_code}: {r.text[:80]}")
                self._gtts(text)
        except Exception as e:
            print(f"[VOICE] ElevenLabs error: {e}")
            self._gtts(text)

    def _openai_tts(self, text: str):
        try:
            import requests
            hdrs = {"Authorization": f"Bearer {self.config.openai_api_key}", "Content-Type": "application/json"}
            body = {"model":"tts-1-hd","input":text,"voice":self.config.openai_tts_voice}
            r = requests.post("https://api.openai.com/v1/audio/speech", json=body, headers=hdrs, timeout=20)
            if r.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f:
                    f.write(r.content); fname=f.name
                self._play_file(fname)
                try: os.unlink(fname)
                except: pass
            else:
                self._gtts(text)
        except Exception:
            self._gtts(text)

    def _gtts(self, text: str):
        try:
            from gtts import gTTS
            import io
            buf = io.BytesIO()
            gTTS(text=text, lang='en', tld='co.uk').write_to_fp(buf)
            with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f:
                f.write(buf.getvalue()); fname=f.name
            self._play_file(fname)
            try: os.unlink(fname)
            except: pass
        except Exception:
            self._pyttsx3(text)

    def _pyttsx3(self, text: str):
        try:
            import pyttsx3
            e = pyttsx3.init()
            e.setProperty('rate', 165); e.setProperty('volume', 0.95)
            for v in e.getProperty('voices') or []:
                if any(x in v.name.lower() for x in ['david','daniel','mark','alex','en_gb']):
                    e.setProperty('voice',v.id); break
            e.say(text); e.runAndWait()
        except Exception: pass

    # ── AUDIO PLAYBACK ────────────────────────────────────────────────────────

    def _play_file(self, path: str):
        """Play audio file — tries pygame → ffplay → mpg123/aplay"""
        if self._stop_event.is_set():
            return

        # Method 1: pygame
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    return
                pygame.time.wait(50)
            return
        except Exception: pass

        # Method 2: ffplay (Linux/Mac — usually available)
        if self._stop_event.is_set(): return
        try:
            proc = subprocess.Popen(
                ["ffplay","-nodisp","-autoexit","-loglevel","quiet", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.terminate(); return
                time.sleep(0.05)
            return
        except FileNotFoundError: pass

        # Method 3: mpg123
        try:
            proc = subprocess.Popen(["mpg123","-q",path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.terminate(); return
                time.sleep(0.05)
            return
        except FileNotFoundError: pass

        # Method 4: Windows Media Player
        if self.system == "Windows":
            try:
                proc = subprocess.Popen(["powershell","-c",
                    f'(New-Object Media.SoundPlayer \"{path}\").PlaySync()'])
                while proc.poll() is None:
                    if self._stop_event.is_set(): proc.terminate(); return
                    time.sleep(0.05)
            except: pass

    def _run_proc(self, cmd):
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            if self._stop_event.is_set():
                proc.terminate(); return
            time.sleep(0.05)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _is_stop_phrase(self, text: str) -> bool:
        t = text.lower().strip()
        return any(p in t for p in self.config.stop_phrases)

    def _clean(self, text: str) -> str:
        text = re.sub(r'<tool>.*?</tool>', '', text, flags=re.DOTALL)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*',     r'\1', text)
        text = re.sub(r'`{1,3}[\s\S]*?`{1,3}', '[code]', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'\.\s*\.+', '.', text)
        # Natural speech length
        if len(text) > 600:
            parts = re.split(r'(?<=[.!?])\s+', text)
            out = ""
            for p in parts:
                if len(out)+len(p) < 560: out += p+" "
                else: break
            text = out.strip()
        return text
