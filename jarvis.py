#!/usr/bin/env python3
"""JARVIS — Just A Rather Very Intelligent System v5"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from core.assistant import JarvisAssistant
from core.config    import Config
from core.memory    import Memory

print("""
  ╔═══════════════════════════════════════╗
  ║  J.A.R.V.I.S  v5  — Daily Driver    ║
  ╚═══════════════════════════════════════╝""")

cfg  = Config()
mem  = Memory()
chain = cfg.get_api_chain()
if not chain:
    print("\n  [ERROR] No API keys in .env\n"); sys.exit(1)

uname = mem.get_user_name()
count = mem.data.get("interaction_count", 0)
print(f"  APIs      : {len(chain)} backend(s) — {', '.join(b for b,k,m in chain)}")
print(f"  Memory    : {len(mem.data.get('facts',{}))} facts stored" +
      (f" | user: {uname}" if uname else "") +
      (f" | {count} sessions" if count else ""))
print(f"  Voice     : {'ElevenLabs' if cfg.elevenlabs_api_key else 'fallback TTS'}")
print()

try:
    asyncio.run(JarvisAssistant(cfg).run())
except KeyboardInterrupt:
    print("\n  JARVIS offline.\n")
