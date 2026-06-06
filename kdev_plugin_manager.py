#!/usr/bin/env python3
"""
KDEV — Plugin + Tool Manifest Manager v1.0
Ported & upgraded from paoloanzn/free-code (skills/ + plugins/) + instructkr/claw-code (port_manifest.py + tools.py + plugin hooks)
Author: Grok (Co-Engineer Partner) — 2026-04-01
"""

import json
import os
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Callable
from datetime import datetime

class KDEVPluginManager:
    def __init__(
        self,
        plugins_dir: str = "/home/yanflare/.kdev/plugins",
        manifest_path: str = "/home/yanflare/.kdev/tool_manifest.json",
        skills_path: str = "/home/yanflare/kdev-deploy/skills.py",  # your existing one
        debug: bool = True
    ):
        self.plugins_dir = Path(plugins_dir)
        self.manifest_path = Path(manifest_path)
        self.skills_path = Path(skills_path)
        self.debug = debug
        self.plugins: Dict[str, Any] = {}
        self.tools: Dict[str, Callable] = {}
        self.hooks = {"pre_execute": [], "post_execute": []}

        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._load_manifest()
        self._auto_discover_plugins()
        if self.debug:
            print(f"[KDEV-PLUGIN] Manager initialized | Tools: {len(self.tools)} | Plugins: {len(self.plugins)}")

    def _load_manifest(self):
        """Load or create unified tool manifest (claw-code style)"""
        if not self.manifest_path.exists():
            default_manifest = {
                "name": "kdev-tool-manifest",
                "version": "1.0",
                "tools": [],
                "plugins": [],
                "last_updated": datetime.now().isoformat()
            }
            self.manifest_path.write_text(json.dumps(default_manifest, indent=2))
        self.manifest = json.loads(self.manifest_path.read_text())

    def _save_manifest(self):
        self.manifest["last_updated"] = datetime.now().isoformat()
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2))

    def _auto_discover_plugins(self):
        """free-code style auto-discovery + claw-code plugin hooks"""
        for file in self.plugins_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(file.stem, str(file))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Register any plugin class or functions marked with @plugin
                if hasattr(module, "PLUGIN_NAME"):
                    self.plugins[module.PLUGIN_NAME] = module
                    self.manifest["plugins"].append(module.PLUGIN_NAME)
                    if self.debug:
                        print(f"[KDEV-PLUGIN] Loaded plugin: {module.PLUGIN_NAME}")

                # Register tools
                if hasattr(module, "register_tools"):
                    module.register_tools(self.register_tool)

            except Exception as e:
                print(f"[KDEV-PLUGIN] Failed to load {file.name}: {e}")

        self._save_manifest()

    def register_tool(self, name: str, func: Callable, description: str = ""):
        """Register a tool (skills.py compatible)"""
        self.tools[name] = func
        self.manifest["tools"].append({
            "id": name,
            "type": "tool",
            "description": description,
            "registered_at": datetime.now().isoformat()
        })
        if self.debug:
            print(f"[KDEV-PLUGIN] Registered tool: {name}")

    def add_hook(self, phase: str, func: Callable):
        """claw-code style pre/post hooks"""
        if phase in self.hooks:
            self.hooks[phase].append(func)

    def execute_tool(self, tool_name: str, *args, **kwargs) -> Any:
        """Execute with full plugin hook pipeline"""
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")

        # Pre-execute hooks (free-code + claw-code)
        for hook in self.hooks["pre_execute"]:
            hook(tool_name, *args, **kwargs)

        result = self.tools[tool_name](*args, **kwargs)

        # Post-execute hooks
        for hook in self.hooks["post_execute"]:
            hook(tool_name, result, *args, **kwargs)

        return result

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    def trigger_agent(self, trigger_type: str, payload: Dict = None):
        """AGENT_TRIGGERS from free-code (simple but powerful)"""
        if self.debug:
            print(f"[KDEV-TRIGGER] Agent trigger fired: {trigger_type} | Payload: {payload}")
        # Example: you can later wire this to KAIROS daemon background tasks
        return {"status": "triggered", "type": trigger_type}

# ─────────────────────────────────────────────────────────────
# QUICK USAGE + AUTO-REGISTER EXISTING SKILLS (backward compatible)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    manager = KDEVPluginManager()

    # Example built-in tools (you can move your existing skills.py logic here)
    def example_git_status():
        return "On branch main • 3 files changed"

    manager.register_tool("git_status", example_git_status, "Returns current git status")

    print(f"Available tools: {manager.list_tools()}")
    print("Drop new .py files into ~/.kdev/plugins/ and they auto-load!")