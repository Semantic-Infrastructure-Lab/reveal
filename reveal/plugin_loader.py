"""
Plugin Loader - YAML-based plugin system for reveal

Loads plugin definitions from YAML files and provides extension-to-analyzer mapping.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class LevelDefinition:
    """Definition of a single reveal level"""
    name: str
    description: str
    breadcrumb: str
    analyzer: Optional[str]
    outputs: List[str] = field(default_factory=list)
    next_levels: List[int] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)
    paging: bool = False
    page_size: int = 120


@dataclass
class PluginDefinition:
    """Complete plugin definition loaded from YAML"""
    extension: List[str]  # Can be single or multiple extensions
    name: str
    description: str
    icon: str
    levels: Dict[int, LevelDefinition]
    features: Dict[str, bool]
    analyzer_config: Dict[str, Any]
    examples: List[Dict[str, str]]

    @classmethod
    def from_yaml(cls, data: dict) -> "PluginDefinition":
        """Create plugin definition from parsed YAML"""
        # Normalize extension to list
        ext = data["extension"]
        if isinstance(ext, str):
            ext = [ext]

        # Parse level definitions
        levels = {}
        for level_num, level_data in data["levels"].items():
            levels[int(level_num)] = LevelDefinition(
                name=level_data["name"],
                description=level_data["description"],
                breadcrumb=level_data["breadcrumb"],
                analyzer=level_data.get("analyzer"),
                outputs=level_data.get("outputs", []),
                next_levels=level_data.get("next_levels", []),
                tips=level_data.get("tips", []),
                paging=level_data.get("paging", False),
                page_size=level_data.get("page_size", 120),
            )

        return cls(
            extension=ext,
            name=data["name"],
            description=data["description"],
            icon=data.get("icon", "📄"),
            levels=levels,
            features=data.get("features", {}),
            analyzer_config=data.get("analyzer_config", {}),
            examples=data.get("examples", []),
        )


class PluginLoader:
    """Loads and manages reveal plugins"""

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        """
        Initialize plugin loader

        Args:
            plugin_dirs: List of directories to search for plugins.
                        Defaults to [<package>/plugins, ~/.config/reveal/plugins]
        """
        self.plugins: Dict[str, PluginDefinition] = {}
        self.extension_map: Dict[str, PluginDefinition] = {}

        if plugin_dirs is None:
            # Default plugin directories
            package_dir = Path(__file__).parent.parent
            plugin_dirs = [
                package_dir / "plugins",
                Path.home() / ".config" / "reveal" / "plugins",
            ]

        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self.load_all_plugins()

    def load_all_plugins(self):
        """Load all plugins from plugin directories"""
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            for yaml_file in plugin_dir.glob("*.yaml"):
                try:
                    self.load_plugin(yaml_file)
                except Exception as e:
                    print(f"Warning: Failed to load plugin {yaml_file}: {e}")

    def load_plugin(self, yaml_path: Path):
        """Load a single plugin from YAML file"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        plugin = PluginDefinition.from_yaml(data)

        # Register plugin
        self.plugins[plugin.name] = plugin

        # Map extensions to plugin
        for ext in plugin.extension:
            self.extension_map[ext] = plugin

    def get_plugin_for_file(self, file_path: str) -> Optional[PluginDefinition]:
        """Get plugin definition for a file based on extension"""
        ext = Path(file_path).suffix.lower()
        return self.extension_map.get(ext)

    def get_plugin_by_name(self, name: str) -> Optional[PluginDefinition]:
        """Get plugin by name"""
        return self.plugins.get(name)

    def list_plugins(self) -> List[str]:
        """List all loaded plugin names"""
        return list(self.plugins.keys())

    def get_supported_extensions(self) -> List[str]:
        """Get list of all supported file extensions"""
        return sorted(self.extension_map.keys())

    def get_level_info(self, file_path: str, level: int) -> Optional[LevelDefinition]:
        """Get level definition for a file at specific level"""
        plugin = self.get_plugin_for_file(file_path)
        if not plugin:
            return None
        return plugin.levels.get(level)

    def get_breadcrumbs(self, file_path: str, current_level: int) -> List[str]:
        """Get breadcrumb navigation hints for current level"""
        plugin = self.get_plugin_for_file(file_path)
        if not plugin or current_level not in plugin.levels:
            return []

        current = plugin.levels[current_level]
        breadcrumbs = []

        for next_level in current.next_levels:
            if next_level in plugin.levels:
                level_def = plugin.levels[next_level]
                breadcrumbs.append(
                    f"  reveal {Path(file_path).name} --level {next_level}  →  {level_def.breadcrumb}"
                )

        return breadcrumbs


# Global plugin loader instance
_plugin_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    """Get or create the global plugin loader instance"""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader
