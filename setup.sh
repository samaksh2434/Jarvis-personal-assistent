#!/bin/bash
# JARVIS Setup — run once after extracting the zip

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   JARVIS Setup — Installing packages     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

OS=$(uname -s 2>/dev/null || echo "Windows")
echo "  OS: $OS"
echo ""

# ── System audio deps ──────────────────────────────────────────────────────
if [ "$OS" = "Linux" ]; then
    echo "  Installing system audio deps..."
    sudo apt-get install -yq portaudio19-dev python3-pyaudio ffmpeg espeak-ng \
        xclip libnotify-bin 2>/dev/null || true
elif [ "$OS" = "Darwin" ]; then
    command -v brew &>/dev/null && brew install portaudio ffmpeg 2>/dev/null || true
fi

# ── Python packages ────────────────────────────────────────────────────────
echo "  Installing Python packages..."

pip install requests python-dotenv --break-system-packages -q 2>/dev/null || \
pip install requests python-dotenv -q 2>/dev/null || true

pip install SpeechRecognition PyAudio --break-system-packages -q 2>/dev/null || \
pip install SpeechRecognition PyAudio -q 2>/dev/null || true

pip install pygame gTTS pyttsx3 --break-system-packages -q 2>/dev/null || \
pip install pygame gTTS pyttsx3 -q 2>/dev/null || true

pip install mss psutil duckduckgo-search pyperclip --break-system-packages -q 2>/dev/null || \
pip install mss psutil duckduckgo-search pyperclip -q 2>/dev/null || true

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║  Done!  Run with:  python3 jarvis.py     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
