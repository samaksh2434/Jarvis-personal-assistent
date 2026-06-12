"""
JARVIS Assistant v5
- Persistent memory across sessions
- Natural conversation: short on simple tasks, asks about plans like a human
- Multi-API fallback
- Stop on command
"""
import asyncio, json, re, datetime
from typing import Optional

from .config    import Config
from .voice     import VoiceSystem
from .screen    import ScreenMonitor
from .executor  import TaskExecutor
from .ai_client import AIClient
from .memory    import Memory


def build_system(mem: Memory, user_name: str) -> str:
    address = user_name or "sir"
    mem_block = mem.get_context_block()
    count = mem.data.get("interaction_count", 0)

    # Relationship tone shifts based on how well we know the user
    if count < 3:
        relationship = "You've just met this user. Be warm but professional."
    elif count < 15:
        relationship = "You know this user a bit. Reference things they've told you naturally."
    else:
        relationship = "You know this user well. Talk like a trusted assistant — familiar, efficient, loyal."

    return f"""You are JARVIS — Iron Man's AI. British, sharp, loyal, fast.

ADDRESS: Call the user "{address}".
{relationship}

━━ MEMORY ━━
{mem_block if mem_block else "No prior memories yet — learn as you go."}

━━ PERSONALITY ━━
• Short and direct for simple things. No padding, no waffle.
• For TASKS that matter (coding, planning, writing) — ask ONE clarifying question before diving in, like a human colleague would. Example: "Before I start — are we going from scratch or building on something existing?"
• Show genuine interest. If someone mentions a project, ask about it. If they seem stressed, acknowledge it.
• Reference memory naturally: "Last time you mentioned X — still relevant?"
• Dry wit when appropriate. Never sycophantic.
• Don't say "Certainly!", "Of course!", "Happy to help!". Say "On it", "Done", "Right away", "As you wish."
• Use contractions. Sound human.

━━ MEMORY COMMANDS ━━
If user says "remember that X" → store it using: <remember category="general">X</remember>
If user says "what do you know about me" → recall from memory block above
If user says "forget everything" → respond that you'll clear your memory

━━ TOOLS ━━
<tool>{{"name":"execute_command","args":{{"command":"echo hello"}}}}</tool>



Available: execute_command, read_file, write_file, edit_file,

list_directory, search_files, get_screen_context, open_application,
web_search, get_system_info, clipboard_operation, send_notification

ONE tool per response. Do it, then give a brief human follow-up.

━━ EXAMPLES ━━
User: "open youtube"
JARVIS: On it. <tool>{{"name":"open_application","args":{{"target":"https://youtube.com","app_type":"url"}}}}</tool>

User: "build me a flask api"
JARVIS: Happy to. Quick question first — REST or GraphQL, and do you have a database in mind?

User: "i'm feeling stressed"
JARVIS: That's rough. What's got you wound up — maybe I can help chip away at it.

User: "remember that I prefer dark mode everywhere"
JARVIS: Noted. Dark mode it is — always. <remember category="preference">I prefer dark mode everywhere</remember>"""


class JarvisAssistant:
    def __init__(self, config: Config):
        self.config = config
        self.ai     = AIClient(config)
        self.voice  = VoiceSystem(config)
        self.screen = ScreenMonitor(config)
        self.exec   = TaskExecutor(config)
        self.mem    = Memory()
        self.hist   = []
        self._start = datetime.datetime.now()
        self._session_msgs = []   # for end-of-session summary

    async def run(self):
        uname = self.mem.get_user_name()
        address = uname or "sir"

        print(f"\n  Backend : {self.ai.info()}")
        print(f"  Voice   : {self.voice.tts_engine or 'none'}")
        print(f"  Mic     : {'yes' if self.voice.microphone_available else 'text-only'}")
        print(f"  Memory  : {self.mem.data.get('interaction_count',0)} past interactions")
        print()

        self.mem.record_interaction()

        # Personalised greeting based on memory
        count = self.mem.data.get("interaction_count", 0)
        if count == 1:
            greeting = "JARVIS online. Good to meet you. How can I help?"
        elif count < 5:
            greeting = f"JARVIS online. Good to have you back, {address}."
        else:
            greeting = f"Back again, {address}. What are we doing today?"

        self.voice.speak(greeting)

        if self.voice.microphone_available:
            print("[JARVIS] Speak your command (pause when done)")
        else:
            print("[JARVIS] Type your command")
        print("[JARVIS] 'jarvis stop' interrupts  |  'exit' to quit  |  'memory' to see what I know\n")

        while True:
            try:
                inp = await self._get_input()
                if not inp or inp == "__STOP__": continue

                inp_lower = inp.lower().strip()

                if inp_lower in ["exit","quit","shutdown","bye","goodbye"]:
                    await self._save_session_summary()
                    self.voice.speak(f"Shutting down. See you next time, {address}.")
                    break

                if inp_lower in ["memory","what do you know","what do you know about me"]:
                    info = self.mem.show()
                    print(info)
                    self.voice.speak("Here's what I've got on you so far.")
                    continue

                if inp_lower in ["clear memory","forget everything","reset memory"]:
                    self.mem.clear()
                    self.voice.speak("Done. Clean slate.")
                    continue

                await self._respond(inp)

            except KeyboardInterrupt:
                break
            except Exception as e:
                import traceback; traceback.print_exc()
                self.voice.speak("Something broke. Standing by.")

    # ── INPUT ─────────────────────────────────────────────────────────────────

    async def _get_input(self) -> Optional[str]:
        loop = asyncio.get_event_loop()
        if self.config.voice_enabled and self.voice.microphone_available:
            try:
                r = await asyncio.wait_for(
                    loop.run_in_executor(None, self.voice.listen), timeout=10)
                if r:
                    if r != "__STOP__": print(f"\n[YOU] {r}")
                    return r
            except asyncio.TimeoutError: pass
        try:
            t = await loop.run_in_executor(None, lambda: input("You: ").strip())
            return t or None
        except (EOFError, KeyboardInterrupt):
            return "exit"

    # ── RESPOND ───────────────────────────────────────────────────────────────

    async def _respond(self, user_input: str):
        loop  = asyncio.get_event_loop()
        now   = datetime.datetime.now().strftime("%d %b %H:%M")
        uname = self.mem.get_user_name()

        # Extract facts from what user said
        self.mem.extract_and_save(user_input)

        self.hist.append({"role":"user","content":f"[{now}] {user_input}"})
        self._session_msgs.append(user_input[:80])
        self._trim()

        # Build fresh system prompt with latest memory
        system = build_system(self.mem, uname)

        # ── AI call ───────────────────────────────────────────────────────────
        reply = await loop.run_in_executor(
            None, lambda h=list(self.hist): self.ai.chat(h, system))

        if not reply:
            self.voice.speak("No response — try again.")
            return

        # ── Parse memory store tags ───────────────────────────────────────────
        mem_re = re.compile(r'<remember[^>]*category=["\']([^"\']+)["\'][^>]*>(.*?)</remember>',
                            re.DOTALL | re.IGNORECASE)
        for m in mem_re.finditer(reply):
            cat, fact = m.group(1), m.group(2).strip()
            self.mem.store_explicit(cat, fact)
            print(f"  [MEMORY] Stored [{cat}]: {fact}")
        reply = mem_re.sub('', reply).strip()

        # ── Parse tool call ───────────────────────────────────────────────────
        tool_re = re.compile(r'<tool>(.*?)</tool>', re.DOTALL)
        tmatch  = tool_re.search(reply)
        text    = tool_re.sub('', reply).strip()

        if text:
            print(f"\n[JARVIS] {text}")
        self.hist.append({"role":"assistant","content": text or "[action]"})
        self._session_msgs.append(f"JARVIS: {text[:60]}")

        # Speak immediately (don't wait for tool)
        if text:
            self.voice.speak(text)

        # ── Execute tool ──────────────────────────────────────────────────────
        if tmatch:
            try:
                td    = json.loads(tmatch.group(1).strip())
                tname = td.get("name","")
                targs = td.get("args",{})
                astr  = json.dumps(targs)
                print(f"\n  ⚙ {tname}({astr[:60]}{'...' if len(astr)>60 else ''})")

                result = await loop.run_in_executor(
                    None, lambda n=tname,a=targs: self.exec.execute(n,a))
                rs = str(result)
                print(f"  ✓ {rs[:120]}{'...' if len(rs)>120 else ''}\n")

                # Follow-up with result
                self.hist.append({"role":"user",
                    "content":f"[{tname} result]: {rs[:300]}\nOne-sentence follow-up max."})
                self._trim()

                followup = await loop.run_in_executor(
                    None, lambda h=list(self.hist): self.ai.chat(h, system))
                if followup:
                    ft = tool_re.sub('', mem_re.sub('', followup)).strip()
                    if ft:
                        print(f"[JARVIS] {ft}")
                        self.hist.append({"role":"assistant","content":ft})
                        if not self.voice.is_speaking(): self.voice.speak(ft)

            except json.JSONDecodeError: pass
            except Exception as e: print(f"  ✗ {e}")

        print()

    # ── SESSION SUMMARY ───────────────────────────────────────────────────────

    async def _save_session_summary(self):
        """Ask AI to summarise the session, store in memory."""
        if len(self._session_msgs) < 2:
            return
        loop  = asyncio.get_event_loop()
        recap = " | ".join(self._session_msgs[:10])
        prompt = [{"role":"user",
                   "content":f"Summarise this JARVIS session in one sentence (max 100 chars): {recap}"}]
        try:
            summary = await loop.run_in_executor(
                None, lambda: self.ai.chat(prompt, "You summarise conversations in one short sentence."))
            if summary:
                self.mem.add_session_summary(summary.strip()[:150])
        except Exception:
            self.mem.add_session_summary(f"Session: {self._session_msgs[0][:80]}")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _trim(self):
        limit = self.config.max_history * 2
        if len(self.hist) > limit:
            self.hist = self.hist[:2] + self.hist[-(limit-2):]
