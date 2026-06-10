#!/usr/bin/env python3
"""
J.A.R.V.I.S — Just A Rather Very Intelligent System
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from core.assistant import JarvisAssistant
from core.config    import Config

BANNER = """
  ╔══════════════════════════════════════════════════╗
  ║    J . A . R . V . I . S                         ║
  ║    Just A Rather Very Intelligent System  v2.0   ║
  ╚══════════════════════════════════════════════════╝
"""

def main():
    print(BANNER)
    cfg = Config()

    if not cfg.get_backend():
        print("  [ERROR] No API key found in .env")
        print()
        print("  ── FREE OPTIONS ──────────────────────────────")
        print("  OpenRouter (free models):  OPENROUTER_API_KEY=...")
        print("  Groq       (free, fast):   GROQ_API_KEY=...")
        print()
        print("  ── VOICE ─────────────────────────────────────")
        print("  ElevenLabs (human voice):  ELEVENLABS_API_KEY=...")
        print()
        print("  Add keys to jarvis/.env and restart.")
        sys.exit(1)

    assistant = JarvisAssistant(cfg)
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        print("\n\n  JARVIS: Shutting down. Goodbye, sir.\n")

if __name__ == "__main__":
    main()
