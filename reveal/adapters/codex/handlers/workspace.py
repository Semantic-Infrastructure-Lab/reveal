"""Workspace resource handlers for the codex:// adapter — skills, plugins (BACK-946).

Parity with claude://agents and claude://hooks: both ~/.codex/skills/ (SKILL.md
per skill, recursive under vendor subdirs like .system/) and the installed-plugin
manifests under ~/.codex/plugins/cache/**/.codex-plugin/plugin.json are the same
kind of "named, described, browsable definition" data claude://agents exposes,
just previously unexposed by codex://.
"""
import json
from pathlib import Path
from typing import Any, Dict
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.results import ResultBuilder


def _parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML-ish frontmatter (name/description) from a SKILL.md file."""
    fm: Dict[str, Any] = {}
    if not content.startswith('---'):
        return fm
    end = content.find('\n---', 3)
    if end < 0:
        return fm
    for line in content[3:end].splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            fm[k.strip()] = v.strip().strip('"')
    return fm


def get_skills(codex_home: Path, resource: str) -> Dict[str, Any]:
    """List or read skill definitions from ~/.codex/skills/**/SKILL.md."""
    skills_dir = codex_home / 'skills'
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_skills',
        source=str(skills_dir),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
    )

    if not skills_dir.exists():
        return {**base, 'skills': [], 'total': 0,
                'error': f'Skills directory not found: {skills_dir}'}

    entries = []
    for skill_md in sorted(skills_dir.glob('**/SKILL.md')):
        try:
            content = skill_md.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        fm = _parse_skill_frontmatter(content)
        name = fm.get('name') or skill_md.parent.name
        entries.append({
            'name': name,
            'description': fm.get('description', ''),
            'path': str(skill_md),
        })

    parts = resource.split('/', 1)
    skill_name = parts[1].strip() if len(parts) > 1 else ''
    if skill_name:
        matches = [e for e in entries if e['name'] == skill_name]
        if not matches:
            return {**base, 'type': 'codex_skill',
                    'error': f'Skill not found: {skill_name}', 'name': skill_name}
        entry = matches[0]
        skill_path = Path(entry['path'])
        try:
            content = skill_path.read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            return {**base, 'type': 'codex_skill', 'error': str(exc), 'name': skill_name}
        return {
            **base,
            'type': 'codex_skill',
            'source': str(skill_path),
            'name': entry['name'],
            'description': entry['description'],
            'content': content,
        }

    return {**base, 'skills': entries, 'total': len(entries)}


def get_plugins(codex_home: Path, resource: str) -> Dict[str, Any]:
    """List or read installed plugin manifests from ~/.codex/plugins/cache/.

    Full glob: ~/.codex/plugins/cache/**/.codex-plugin/plugin.json
    """
    plugins_dir = codex_home / 'plugins'
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_plugins',
        source=str(plugins_dir),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
    )

    if not plugins_dir.exists():
        return {**base, 'plugins': [], 'total': 0,
                'error': f'Plugins directory not found: {plugins_dir}'}

    entries = []
    for manifest_path in sorted(plugins_dir.glob('**/.codex-plugin/plugin.json')):
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8', errors='replace'))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append({
            'name': manifest.get('name', manifest_path.parent.parent.name),
            'version': manifest.get('version', ''),
            'description': manifest.get('description', ''),
            'path': str(manifest_path),
        })

    parts = resource.split('/', 1)
    plugin_name = parts[1].strip() if len(parts) > 1 else ''
    if plugin_name:
        matches = [e for e in entries if e['name'] == plugin_name]
        if not matches:
            return {**base, 'type': 'codex_plugin',
                    'error': f'Plugin not found: {plugin_name}', 'name': plugin_name}
        entry = matches[0]
        manifest_path = Path(entry['path'])
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8', errors='replace'))
        except (OSError, json.JSONDecodeError) as exc:
            return {**base, 'type': 'codex_plugin', 'error': str(exc), 'name': plugin_name}
        return {
            **base,
            'type': 'codex_plugin',
            'source': str(manifest_path),
            'name': entry['name'],
            'manifest': manifest,
        }

    return {**base, 'plugins': entries, 'total': len(entries)}
