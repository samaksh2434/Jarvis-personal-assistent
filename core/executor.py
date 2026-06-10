"""
JARVIS Task Executor
Handles all tool/skill execution: files, commands, screen, system info, web, etc.
"""

import os
import subprocess
import shutil
import json
import base64
import platform
import fnmatch
from pathlib import Path
from typing import Any, Dict
from datetime import datetime


class TaskExecutor:
    def __init__(self, config):
        self.config = config
        self.system = platform.system()  # "Linux", "Darwin", "Windows"
        self.home = Path.home()

    def execute(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Route to the correct tool handler"""
        handlers = {
            "execute_command": self.execute_command,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "list_directory": self.list_directory,
            "search_files": self.search_files,
            "get_screen_context": self.get_screen_context,
            "open_application": self.open_application,
            "web_search": self.web_search,
            "get_system_info": self.get_system_info,
            "clipboard_operation": self.clipboard_operation,
            "send_notification": self.send_notification,
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return f"Unknown tool: {tool_name}"
        
        try:
            return handler(**tool_input)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    # ─── COMMAND EXECUTION ────────────────────────────────────────────────────

    def execute_command(self, command: str, working_dir: str = None, timeout: int = 60) -> str:
        """Execute shell command safely"""
        cwd = Path(working_dir).expanduser() if working_dir else self.home
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd)
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            return output.strip() or "Command executed successfully (no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Command failed: {str(e)}"

    # ─── FILE OPERATIONS ──────────────────────────────────────────────────────

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve path, handling ~, relative paths"""
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = self.home / p
        return p

    def read_file(self, path: str) -> str:
        """Read file contents"""
        p = self._resolve_path(path)
        if not p.exists():
            return f"File not found: {p}"
        
        # Check file size
        size = p.stat().st_size
        if size > 5 * 1024 * 1024:  # 5MB limit
            return f"File too large ({size // 1024}KB). Reading first 2000 lines...\n" + \
                   "\n".join(p.read_text(errors='replace').splitlines()[:2000])
        
        try:
            return p.read_text(errors='replace')
        except UnicodeDecodeError:
            return f"Binary file at {p} — {size} bytes"

    def write_file(self, path: str, content: str) -> str:
        """Write/create a file"""
        p = self._resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Successfully wrote {len(content)} characters to {p}"

    def edit_file(self, path: str, operation: str, find_text: str = None, 
                  new_text: str = None, line_number: int = None) -> str:
        """Targeted file editing"""
        p = self._resolve_path(path)
        if not p.exists():
            return f"File not found: {p}"
        
        content = p.read_text(errors='replace')
        lines = content.splitlines(keepends=True)
        original = content
        
        if operation == "replace":
            if find_text is None:
                return "Error: find_text required for replace operation"
            if find_text not in content:
                return f"Text not found in file: '{find_text[:50]}'"
            content = content.replace(find_text, new_text or "", 1)
            
        elif operation == "append":
            content = content + "\n" + (new_text or "")
            
        elif operation == "prepend":
            content = (new_text or "") + "\n" + content
            
        elif operation == "insert_after":
            if find_text and find_text in content:
                content = content.replace(find_text, find_text + "\n" + (new_text or ""), 1)
            elif line_number and 0 < line_number <= len(lines):
                lines.insert(line_number, (new_text or "") + "\n")
                content = "".join(lines)
                
        elif operation == "insert_before":
            if find_text and find_text in content:
                content = content.replace(find_text, (new_text or "") + "\n" + find_text, 1)
            elif line_number and 0 < line_number <= len(lines):
                lines.insert(line_number - 1, (new_text or "") + "\n")
                content = "".join(lines)
                
        elif operation == "delete_line":
            if line_number and 0 < line_number <= len(lines):
                lines.pop(line_number - 1)
                content = "".join(lines)
        
        if content != original:
            p.write_text(content)
            return f"File edited successfully: {p}"
        else:
            return "No changes made (text may not have been found)"

    def list_directory(self, path: str = None, show_hidden: bool = False) -> str:
        """List directory contents"""
        p = self._resolve_path(path) if path else self.home
        
        if not p.exists():
            return f"Directory not found: {p}"
        if not p.is_dir():
            return f"Not a directory: {p}"
        
        items = []
        for item in sorted(p.iterdir()):
            if not show_hidden and item.name.startswith('.'):
                continue
            size = ""
            if item.is_file():
                s = item.stat().st_size
                if s > 1024 * 1024:
                    size = f" ({s // 1024 // 1024}MB)"
                elif s > 1024:
                    size = f" ({s // 1024}KB)"
                else:
                    size = f" ({s}B)"
            
            icon = "📁" if item.is_dir() else "📄"
            items.append(f"{icon} {item.name}{size}")
        
        return f"Contents of {p}:\n" + "\n".join(items) if items else f"Empty directory: {p}"

    def search_files(self, query: str, search_path: str = None, 
                     search_content: bool = False, file_type: str = None) -> str:
        """Search for files by name or content"""
        base = self._resolve_path(search_path) if search_path else self.home
        results = []
        
        # Limit search to prevent timeouts
        count = 0
        max_files = 500
        
        for root, dirs, files in os.walk(base):
            # Skip hidden and system dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') 
                       and d not in ['node_modules', '__pycache__', '.git', 'venv', '.venv']]
            
            for filename in files:
                if count >= max_files:
                    break
                    
                if file_type and not filename.endswith(file_type):
                    continue
                    
                filepath = Path(root) / filename
                
                # Name match
                if fnmatch.fnmatch(filename.lower(), f"*{query.lower()}*"):
                    results.append(str(filepath))
                    count += 1
                    continue
                
                # Content search
                if search_content:
                    try:
                        text = filepath.read_text(errors='replace')
                        if query.lower() in text.lower():
                            results.append(f"{filepath} [content match]")
                            count += 1
                    except Exception:
                        pass
            
            if count >= max_files:
                break
        
        if results:
            return f"Found {len(results)} result(s):\n" + "\n".join(results[:50])
        return f"No files found matching '{query}'"

    # ─── SCREEN MONITORING ────────────────────────────────────────────────────

    def get_screen_context(self, question: str = None) -> str:
        """Capture and analyze screen"""
        try:
            import mss
            import mss.tools
            import anthropic
            
            with mss.mss() as sct:
                # Capture primary monitor
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                
                # Convert to PNG bytes
                png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                img_b64 = base64.b64encode(png_bytes).decode()
            
            # Analyze with Claude Vision
            client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            
            prompt = question or "Describe what is currently visible on this screen in detail. What application is open? What content is visible? What is the user doing?"
            
            response = client.messages.create(
                model="claude-opus-4-5",  # Vision-capable model
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            )
            
            return response.content[0].text
            
        except ImportError:
            return "Screen capture requires 'mss' package. Run: pip install mss"
        except Exception as e:
            return f"Screen capture failed: {str(e)}"

    # ─── APPLICATIONS ─────────────────────────────────────────────────────────

    def open_application(self, target: str, app_type: str = "app") -> str:
        """Open an application, URL, or file"""
        try:
            if self.system == "Darwin":  # macOS
                if app_type == "url":
                    subprocess.Popen(["open", target])
                else:
                    subprocess.Popen(["open", target])
                    
            elif self.system == "Linux":
                if app_type == "url":
                    subprocess.Popen(["xdg-open", target])
                else:
                    # Try common launchers
                    subprocess.Popen(["xdg-open", target])
                    
            elif self.system == "Windows":
                os.startfile(target)
            
            return f"Opened: {target}"
        except Exception as e:
            return f"Failed to open {target}: {str(e)}"

    # ─── WEB SEARCH ───────────────────────────────────────────────────────────

    def web_search(self, query: str, num_results: int = 5) -> str:
        """Search the web using DuckDuckGo (no API key needed)"""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num_results):
                    results.append(f"**{r['title']}**\n{r['href']}\n{r['body']}\n")
            
            if results:
                return f"Search results for '{query}':\n\n" + "\n".join(results)
            return f"No results found for '{query}'"
            
        except ImportError:
            # Fallback: use subprocess curl with DuckDuckGo
            return self._web_search_fallback(query)
        except Exception as e:
            return f"Search failed: {str(e)}"

    def _web_search_fallback(self, query: str) -> str:
        """Fallback web search using curl"""
        try:
            result = subprocess.run(
                ['curl', '-s', '-A', 'Mozilla/5.0', 
                 f'https://api.duckduckgo.com/?q={query.replace(" ", "+")}&format=json&no_html=1'],
                capture_output=True, text=True, timeout=10
            )
            data = json.loads(result.stdout)
            
            output = []
            if data.get('AbstractText'):
                output.append(f"Summary: {data['AbstractText']}")
            for topic in data.get('RelatedTopics', [])[:5]:
                if 'Text' in topic:
                    output.append(f"• {topic['Text']}")
            
            return "\n".join(output) if output else f"Search for: {query} — install duckduckgo-search for better results"
        except Exception as e:
            return f"Search unavailable: {str(e)}"

    # ─── SYSTEM INFORMATION ───────────────────────────────────────────────────

    def get_system_info(self, info_type: str = "all") -> str:
        """Get system information"""
        try:
            import psutil
            
            info = {}
            
            if info_type in ["all", "cpu"]:
                info["CPU"] = {
                    "usage_percent": psutil.cpu_percent(interval=1),
                    "cores": psutil.cpu_count(),
                    "freq_mhz": round(psutil.cpu_freq().current) if psutil.cpu_freq() else "N/A"
                }
            
            if info_type in ["all", "memory"]:
                mem = psutil.virtual_memory()
                info["Memory"] = {
                    "total_gb": round(mem.total / 1e9, 1),
                    "used_gb": round(mem.used / 1e9, 1),
                    "percent": mem.percent
                }
            
            if info_type in ["all", "battery"]:
                battery = psutil.sensors_battery()
                if battery:
                    info["Battery"] = {
                        "percent": battery.percent,
                        "charging": battery.power_plugged,
                        "time_left": f"{battery.secsleft // 3600}h {(battery.secsleft % 3600) // 60}m" 
                                     if battery.secsleft > 0 else "Calculating"
                    }
            
            if info_type in ["all", "disk"]:
                disk = psutil.disk_usage('/')
                info["Disk"] = {
                    "total_gb": round(disk.total / 1e9, 1),
                    "used_gb": round(disk.used / 1e9, 1),
                    "free_gb": round(disk.free / 1e9, 1),
                    "percent": disk.percent
                }
            
            if info_type in ["all", "processes"]:
                procs = []
                for proc in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                                   key=lambda p: p.info.get('cpu_percent', 0) or 0,
                                   reverse=True)[:10]:
                    procs.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "cpu%": round(proc.info['cpu_percent'] or 0, 1),
                        "mem%": round(proc.info['memory_percent'] or 0, 1)
                    })
                info["Top Processes"] = procs
            
            if info_type in ["all", "network"]:
                net = psutil.net_io_counters()
                info["Network"] = {
                    "bytes_sent_mb": round(net.bytes_sent / 1e6, 1),
                    "bytes_recv_mb": round(net.bytes_recv / 1e6, 1)
                }
            
            return json.dumps(info, indent=2)
            
        except ImportError:
            # Fallback using system commands
            return self._system_info_fallback(info_type)

    def _system_info_fallback(self, info_type: str) -> str:
        """Fallback system info without psutil"""
        results = []
        
        if self.system == "Linux":
            commands = {
                "cpu": "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
                "memory": "free -h",
                "disk": "df -h /",
                "processes": "ps aux --sort=-%cpu | head -10"
            }
            
            for key, cmd in commands.items():
                if info_type in ["all", key]:
                    out = self.execute_command(cmd)
                    results.append(f"{key.upper()}:\n{out}")
        
        elif self.system == "Darwin":
            if info_type in ["all", "memory"]:
                results.append(self.execute_command("vm_stat"))
            if info_type in ["all", "cpu"]:
                results.append(self.execute_command("top -l 1 | head -20"))
        
        elif self.system == "Windows":
            if info_type in ["all", "cpu", "memory"]:
                results.append(self.execute_command("systeminfo | findstr /C:\"Total Physical Memory\" /C:\"Available Physical Memory\""))
        
        return "\n".join(results) if results else "System info unavailable"

    # ─── CLIPBOARD ────────────────────────────────────────────────────────────

    def clipboard_operation(self, operation: str, content: str = None) -> str:
        """Read or write clipboard"""
        try:
            import pyperclip
            
            if operation == "read":
                text = pyperclip.paste()
                return f"Clipboard contents:\n{text}"
            elif operation == "write":
                pyperclip.copy(content or "")
                return f"Copied to clipboard: {(content or '')[:100]}"
                
        except ImportError:
            # Platform fallbacks
            if operation == "read":
                if self.system == "Linux":
                    result = self.execute_command("xclip -selection clipboard -o 2>/dev/null || xsel --clipboard --output 2>/dev/null")
                    return f"Clipboard: {result}"
                elif self.system == "Darwin":
                    result = self.execute_command("pbpaste")
                    return f"Clipboard: {result}"
                elif self.system == "Windows":
                    result = self.execute_command("powershell -command Get-Clipboard")
                    return f"Clipboard: {result}"
            elif operation == "write":
                if self.system == "Linux":
                    self.execute_command(f"echo '{content}' | xclip -selection clipboard")
                elif self.system == "Darwin":
                    self.execute_command(f"echo '{content}' | pbcopy")
                elif self.system == "Windows":
                    self.execute_command(f"echo {content} | clip")
                return f"Copied to clipboard"

    # ─── NOTIFICATIONS ────────────────────────────────────────────────────────

    def send_notification(self, title: str, message: str, urgency: str = "normal") -> str:
        """Send desktop notification"""
        try:
            if self.system == "Linux":
                self.execute_command(f'notify-send "{title}" "{message}" --urgency={urgency}')
            elif self.system == "Darwin":
                self.execute_command(
                    f'osascript -e \'display notification "{message}" with title "{title}"\''
                )
            elif self.system == "Windows":
                self.execute_command(
                    f'powershell -command "[System.Windows.Forms.MessageBox]::Show(\'{message}\', \'{title}\')"'
                )
            return f"Notification sent: {title}"
        except Exception as e:
            return f"Notification failed: {str(e)}"
