"""
Breadcrumb Navigation System

Provides navigation hints and level suggestions for reveal output.
This is a key feature for agentic AI - always showing what other views are available.
"""

from typing import List, Optional
from pathlib import Path


class BreadcrumbNavigator:
    """Generates breadcrumb navigation hints for reveal levels"""

    def __init__(self, file_path: str, current_level: int, plugin_loader):
        """
        Initialize breadcrumb navigator

        Args:
            file_path: Path to the file being revealed
            current_level: Current revelation level (0-3)
            plugin_loader: PluginLoader instance
        """
        self.file_path = file_path
        self.current_level = current_level
        self.plugin_loader = plugin_loader
        self.plugin = plugin_loader.get_plugin_for_file(file_path)

    def get_current_level_info(self) -> Optional[dict]:
        """Get information about the current level"""
        if not self.plugin or self.current_level not in self.plugin.levels:
            return None

        level = self.plugin.levels[self.current_level]
        return {
            "name": level.name,
            "description": level.description,
            "breadcrumb": level.breadcrumb,
        }

    def get_navigation_hints(self) -> List[str]:
        """Get list of available navigation options from current level"""
        if not self.plugin or self.current_level not in self.plugin.levels:
            return []

        current = self.plugin.levels[self.current_level]
        hints = []

        for next_level in current.next_levels:
            if next_level in self.plugin.levels:
                level_def = self.plugin.levels[next_level]
                hints.append({
                    "level": next_level,
                    "name": level_def.name,
                    "description": level_def.breadcrumb,
                    "command": f"reveal {Path(self.file_path).name} --level {next_level}",
                })

        return hints

    def get_tips(self) -> List[str]:
        """Get tips for the current level"""
        if not self.plugin or self.current_level not in self.plugin.levels:
            return []

        return self.plugin.levels[self.current_level].tips

    def format_header(self) -> str:
        """Format a header showing current location in hierarchy"""
        if not self.plugin:
            return f"📄 {Path(self.file_path).name}"

        level_info = self.get_current_level_info()
        if not level_info:
            return f"📄 {Path(self.file_path).name}"

        icon = self.plugin.icon
        name = Path(self.file_path).name
        level_name = level_info["name"].title()
        level_desc = level_info["description"]

        return f"{icon} {name} (Level {self.current_level}: {level_name})\n{'─' * 60}\n{level_desc}"

    def format_footer(self, include_tips: bool = True) -> str:
        """Format a footer with navigation hints and tips"""
        parts = []

        # Navigation section
        hints = self.get_navigation_hints()
        if hints:
            parts.append("\n💡 Navigation:")
            for hint in hints:
                parts.append(f"   {hint['command']:40} → {hint['description']}")

        # Tips section
        if include_tips:
            tips = self.get_tips()
            if tips:
                parts.append("\n💬 Tips:")
                for tip in tips:
                    parts.append(f"   • {tip}")

        return "\n".join(parts) if parts else ""

    def format_complete_output(self, content: str, show_tips: bool = True) -> str:
        """
        Format complete output with header, content, and footer

        Args:
            content: The main content to display
            show_tips: Whether to show tips in footer

        Returns:
            Formatted output with navigation breadcrumbs
        """
        parts = [
            self.format_header(),
            "",
            content,
            self.format_footer(include_tips=show_tips),
        ]

        return "\n".join(parts)


def format_with_breadcrumbs(
    file_path: str,
    level: int,
    content: str,
    plugin_loader,
    show_tips: bool = True,
) -> str:
    """
    Convenience function to format output with breadcrumbs

    Args:
        file_path: Path to file
        level: Current revelation level
        content: Content to display
        plugin_loader: PluginLoader instance
        show_tips: Whether to show tips

    Returns:
        Formatted output with navigation
    """
    navigator = BreadcrumbNavigator(file_path, level, plugin_loader)
    return navigator.format_complete_output(content, show_tips)
