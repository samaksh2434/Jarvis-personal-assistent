"""
JARVIS Screen Monitor
Continuously monitors the screen and provides context when asked
"""

import threading
import time
import base64
from typing import Optional


class ScreenMonitor:
    def __init__(self, config):
        self.config = config
        self.current_screenshot_b64: Optional[str] = None
        self.last_capture_time = 0
        self.monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        if config.screen_monitor_enabled:
            self._start_monitoring()

    def _start_monitoring(self):
        """Start background screen capture"""
        try:
            import mss
            self.monitoring = True
            self._monitor_thread = threading.Thread(
                target=self._capture_loop, daemon=True
            )
            self._monitor_thread.start()
            print("[SCREEN] Screen monitor active ✓")
        except ImportError:
            print("[SCREEN] mss not installed — screen monitoring disabled")
            print("         Install: pip install mss")

    def _capture_loop(self):
        """Background loop to periodically capture screen"""
        import mss
        import mss.tools
        
        while self.monitoring:
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]  # Primary monitor
                    screenshot = sct.grab(monitor)
                    png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                    self.current_screenshot_b64 = base64.b64encode(png_bytes).decode()
                    self.last_capture_time = time.time()
            except Exception:
                pass
            
            time.sleep(self.config.screen_capture_interval)

    def get_current_screenshot(self) -> Optional[str]:
        """Get the most recent screenshot as base64"""
        return self.current_screenshot_b64

    def capture_now(self) -> Optional[str]:
        """Force an immediate screen capture"""
        try:
            import mss
            import mss.tools
            
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                return base64.b64encode(png_bytes).decode()
        except Exception:
            return None

    def stop(self):
        self.monitoring = False
