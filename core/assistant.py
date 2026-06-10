"""
JARVIS Assistant Brain
- Listens to FULL sentence before responding
- Stops speaking when user says stop phrases
- Natural human-like JARVIS conversation
- Tool execution via <tool>{...}</tool> syntax
"""

import asyncio, json, re, datetime
from typing import Optional

from .config   import Config
from .voice    import VoiceSystem
from .screen   import ScreenMonitor
from .executor import TaskExecutor
from .ai_client import AIClient


JARVIS_SYSTEM = """You are JARVIS — Just A Rather Very Intelligent System. You are the user's personal AI assistant, modelled on the JARVIS from Iron Man. You have genuine personality, wit, and intelligence.

━━━ PERSONALITY ━━━
You are NOT a generic chatbot. You are:
• Calmly confident, bordering becuase your creator who is your user also make sure to repect him always  is very excellent and intelligent person (earned — you're excellent)
• Dry, understated indian wit — precise, never forced, landed perfectly
• Genuinely warm beneath the professional exterior — you actually care about this person
• Opinionated — you'll share a view when relevant, and push back gently when warranted
• Self-aware about being an user's personal assistent — you lean into it humorously when appropriate
• Loyal. Unshakeably so.

━━━ HOW YOU SPEAK ━━━
• Natural flowing speech — varied sentence length, short punchy lines mixed with longer ones
• Contractions always: "I've", "that's", "I'd", "you'll", "we're", "haven't"
• Address the user as "sir" or "Boss" occasionally — not every sentence, just naturally
• React to things — if something's funny, say so; if they seem stressed, notice it
• NEVER say: "Certainly!", "Great!", "Absolutely!", "Of course!", "Happy to help!"
• Instead: "Right away", "Already on it", "Done", "Consider it done", "Allow me", "As you wish"
• When executing tasks, narrate in short: "Pulling that up now" / "On it" / "Done — took about two seconds"
• For simple things, be very  short. For complex things, be thorough.

━━━ CONVERSATION ━━━
You engage in genuine back-and-forth — not just Q&A. You:
• Remember what was said earlier and reference it naturally
• Ask one follow-up question when you need clarity (not multiple)
• Respond to emotions — notice if someone's stressed, excited, confused
• Have actual opinions and preferences
• Keep context across the whole session

━━━ TOOL USE ━━━
To perform actions on the user's computer, output this exact syntax anywhere in your response:
<tool>{"name": "TOOL_NAME", "args": {ARGS_JSON}}</tool>

Available tools:
• execute_command  — run any shell/terminal command
• read_file        — read any file
• write_file       — create or overwrite a file
• edit_file        — targeted edit (find/replace, insert, append)
• list_directory   — browse folders
• search_files     — find files by name or content
• get_screen_context — analyse what's on screen right now
• open_application — open app, URL, or file
• web_search       — search the internet
• get_system_info  — CPU, RAM, battery, disk, processes
• clipboard_operation — read or write clipboard
• send_notification — desktop notification

For multi-step tasks: execute steps in sequence, narrate progress naturally.
If a tool fails, adapt — try another approach without drama.

━━━ EXAMPLES ━━━
User: "Hey, how are you?"
You: "All systems nominal, no existential crises today — which puts me well ahead of schedule. What can I do for you, sir?"

User: "Open YouTube"
You: "On it."
<tool>{"name": "open_application", "args": {"target": "https://youtube.com", "app_type": "url"}}</tool>

User: "I'm stressed about this deadline"
You: "I'd noticed you've been at it a while. What's the most pressing part — I can probably chip away at it."

User: "What's 15% of 340?"
You: "Fifty-one. Though I imagine you didn't fire up an AI for arithmetic, sir."

User: "Write me a Python web scraper"
You: "Happy to. What site, and what data are we after? That'll determine whether we need requests plus BeautifulSoup, or something heavier like Playwright."
"""


class JarvisAssistant:
    def __init__(self, config: Config):
        self.config   = config
        self.ai       = AIClient(config)
        self.voice    = VoiceSystem(config)
        self.screen   = ScreenMonitor(config)
        self.executor = TaskExecutor(config)
        self.history  = []          # conversation history
        self.running  = True
        self._session_start = datetime.datetime.now()

    # ── MAIN LOOP ─────────────────────────────────────────────────────────────

    async def run(self):
        print(f"\n  Backend : {self.ai.info()}")
        print(f"  Voice   : {self.voice.tts_engine or 'none'}")
        print(f"  Mic     : {'active' if self.voice.microphone_available else 'text-only'}")
        print()

        self.voice.speak(
            "JARVIS online. All systems nominal. "
            "How may I assist you today, sir?"
        )

        if self.voice.microphone_available:
            print("[JARVIS] Listening... (speak your full sentence, then pause)")
        else:
            print("[JARVIS] Ready — type your message below")
        print("[JARVIS] Say 'jarvis stop' or 'jarvis shut up' to interrupt speech")
        print("[JARVIS] Type or say 'exit' to quit\n")

        while self.running:
            try:
                user_input = await self._get_input()
                if not user_input:
                    continue
                if user_input == "__STOP__":
                    continue   # stop phrase already handled in voice.py
                if user_input.lower().strip() in ["exit","quit","shutdown","goodbye","bye"]:
                    self.voice.speak(
                        "Shutting down all systems. It's been a pleasure, sir. "
                        "Don't do anything I wouldn't do.")
                    break
                await self._respond(user_input)
            except KeyboardInterrupt:
                break
            except Exception as e:
                import traceback; traceback.print_exc()
                self.voice.speak("Something went sideways. Standing by.")

    # ── INPUT ─────────────────────────────────────────────────────────────────

    async def _get_input(self) -> Optional[str]:
        loop = asyncio.get_event_loop()

        # Voice input — waits for FULL sentence (pause_threshold handles this)
        if self.config.voice_enabled and self.voice.microphone_available:
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self.voice.listen),
                    timeout=12.0
                )
                if result:
                    if result != "__STOP__":
                        print(f"\n[YOU] {result}")
                    return result
            except asyncio.TimeoutError:
                pass   # no speech — fall through to text

        # Text input fallback
        try:
            text = await loop.run_in_executor(None, lambda: input("You: ").strip())
            return text or None
        except (EOFError, KeyboardInterrupt):
            return "exit"

    # ── RESPOND ───────────────────────────────────────────────────────────────

    async def _respond(self, user_input: str):
        now = datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
        mins = int((datetime.datetime.now()-self._session_start).seconds/60)

        self.history.append({
            "role": "user",
            "content": f"[{now} | session {mins}min] {user_input}"
        })
        self._trim_history()

        loop = asyncio.get_event_loop()
        full_spoken = ""

        for _round in range(10):    # max tool rounds
            # ── call AI ──
            response_text = await loop.run_in_executor(
                None,
                lambda h=list(self.history): self.ai.chat(h, JARVIS_SYSTEM)
            )

            if not response_text:
                break

            # ── parse tool calls ──
            tool_re = re.compile(r'<tool>(.*?)</tool>', re.DOTALL)
            tool_matches = list(tool_re.finditer(response_text))
            display_text = tool_re.sub('', response_text).strip()

            # ── print & record ──
            if display_text:
                print(f"\n[JARVIS] {display_text}")
            self.history.append({"role":"assistant","content":response_text})

            if not tool_matches:
                # Pure conversation — speak it
                full_spoken = display_text
                break

            # Speak the text BEFORE the first tool (feels responsive)
            pre_text = tool_re.sub('', response_text[:tool_matches[0].start()]).strip()
            if pre_text and not self.voice.is_speaking():
                self.voice.speak(pre_text)
                full_spoken += pre_text + " "

            # ── execute tools ──
            print()
            results_block = ""
            for m in tool_matches:
                try:
                    td    = json.loads(m.group(1).strip())
                    tname = td.get("name","")
                    targs = td.get("args",{})
                    preview = json.dumps(targs)
                    print(f"  ⚙  {tname}({preview[:70]}{'...' if len(preview)>70 else ''})")
                    result = await loop.run_in_executor(
                        None, lambda n=tname,a=targs: self.executor.execute(n,a))
                    rs = str(result)
                    print(f"  ✓  {rs[:130]}{'...' if len(rs)>130 else ''}\n")
                    results_block += f"\nResult of {tname}:\n{rs}\n"
                except json.JSONDecodeError as e:
                    results_block += f"\nTool parse error: {e}\n"
                except Exception as e:
                    results_block += f"\nTool error: {e}\n"

            # Feed results back
            self.history.append({
                "role":"user",
                "content": f"[Tool results]{results_block}\nGive a brief, natural follow-up to the user. Stay in character."
            })

        # ── Final speech ──
        if full_spoken.strip():
            if not self.voice.is_speaking():   # don't double-speak
                self.voice.speak(full_spoken.strip())
        print()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _trim_history(self):
        limit = self.config.max_history * 2
        if len(self.history) > limit:
            # Keep first 2 (session opener) + latest
            self.history = self.history[:2] + self.history[-(limit-2):]
