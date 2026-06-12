"""
JARVIS Memory System
- Persists facts about the user across sessions (JSON file)
- Auto-extracts facts from conversation (name, job, habits, preferences)
- Injects relevant memories into every prompt
- Remembers recent session summaries
"""
import json, re, os
from pathlib import Path
from datetime import datetime
from typing import List


MEMORY_FILE = Path(__file__).parent.parent / "memory.json"

# What JARVIS tries to learn and remember
FACT_CATEGORIES = {
    "name":        ["my name is","call me","i'm called","i am called"],
    "job":         ["i work","i'm a","i am a","my job","my profession","i do "],
    "location":    ["i live in","i'm from","i'm in","i am in","i am based"],
    "hobby":       ["i like","i love","i enjoy","i play","i watch","my hobby"],
    "project":     ["i'm working on","i'm building","my project","my app","my startup"],
    "preference":  ["i prefer","i always","i usually","i hate","i don't like"],
    "schedule":    ["i wake up","i sleep","my routine","every day i","i work from"],
    "goal":        ["my goal","i want to","i'm trying to","i plan to","i hope to"],
    "health":      ["i have","my health","i'm allergic","i take","my diet"],
    "tech":        ["i use","my setup","my pc","my laptop","i code in","i program"],
}


class Memory:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except Exception:
                pass
        return {
            "facts": {},          # {category: [fact_strings]}
            "sessions": [],       # last N session summaries
            "last_seen": None,
            "interaction_count": 0,
        }

    def save(self):
        try:
            MEMORY_FILE.write_text(json.dumps(self.data, indent=2))
        except Exception as e:
            print(f"[MEMORY] Save failed: {e}")

    # ── FACT EXTRACTION ───────────────────────────────────────────────────────

    def extract_and_save(self, text: str):
        """Scan user message for personal facts and store them."""
        tl = text.lower()
        for category, triggers in FACT_CATEGORIES.items():
            for trigger in triggers:
                if trigger in tl:
                    idx = tl.find(trigger)
                    # grab the phrase starting at trigger, up to 80 chars
                    snippet = text[idx:idx+80].strip()
                    # clean to first sentence end
                    snippet = re.split(r'[.!?\n]', snippet)[0].strip()
                    if len(snippet) > 8:
                        facts = self.data["facts"].setdefault(category, [])
                        # avoid near-duplicates
                        if not any(snippet.lower() in f.lower() or
                                   f.lower() in snippet.lower()
                                   for f in facts):
                            facts.append(snippet)
                            if len(facts) > 5:
                                facts.pop(0)   # keep only last 5 per category
                            self.save()
                        break

    def record_interaction(self):
        self.data["interaction_count"] = self.data.get("interaction_count",0) + 1
        self.data["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save()

    def add_session_summary(self, summary: str):
        sessions = self.data.setdefault("sessions", [])
        sessions.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": summary[:300]
        })
        # Keep last 10 sessions
        if len(sessions) > 10:
            self.data["sessions"] = sessions[-10:]
        self.save()

    def store_explicit(self, category: str, fact: str):
        """Manually store a fact (e.g. from user saying 'remember that...')"""
        facts = self.data["facts"].setdefault(category, [])
        facts.append(fact.strip()[:100])
        if len(facts) > 5: facts.pop(0)
        self.save()

    # ── RECALL ────────────────────────────────────────────────────────────────

    def get_context_block(self) -> str:
        """Return a compact memory block to inject into system prompt."""
        lines = []

        # Personal facts
        facts = self.data.get("facts", {})
        if facts:
            lines.append("What I know about the user:")
            for cat, items in facts.items():
                if items:
                    lines.append(f"  {cat}: {items[-1]}")   # most recent fact

        # Recent sessions
        sessions = self.data.get("sessions", [])
        if sessions:
            lines.append("Recent sessions:")
            for s in sessions[-3:]:
                lines.append(f"  [{s['date']}] {s['summary']}")

        # Relationship context
        count = self.data.get("interaction_count", 0)
        last  = self.data.get("last_seen", "")
        if count > 0:
            lines.append(f"We've talked {count} times. Last seen: {last}.")

        return "\n".join(lines) if lines else ""

    def get_user_name(self) -> str:
        names = self.data.get("facts", {}).get("name", [])
        if names:
            # extract just the name part
            n = names[-1]
            for trigger in ["my name is","call me","i'm called","i am called"]:
                if trigger in n.lower():
                    return n[n.lower().find(trigger)+len(trigger):].strip().split()[0].capitalize()
        return ""

    def has_memory(self) -> bool:
        return bool(self.data.get("facts") or self.data.get("sessions"))

    def clear(self):
        self.data = {"facts":{},"sessions":[],"last_seen":None,"interaction_count":0}
        self.save()
        print("[MEMORY] Cleared.")

    def show(self) -> str:
        if not self.has_memory():
            return "No memories yet."
        lines = ["=== JARVIS Memory ==="]
        for cat, items in self.data.get("facts",{}).items():
            for item in items:
                lines.append(f"  [{cat}] {item}")
        for s in self.data.get("sessions",[])[-5:]:
            lines.append(f"  [session {s['date']}] {s['summary']}")
        lines.append(f"  [interactions] {self.data.get('interaction_count',0)}")
        return "\n".join(lines)
