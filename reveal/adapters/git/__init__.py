"""Git repository inspection adapter.

Provides progressive disclosure for Git repositories:
- Repository overview (branches, tags, commits)
- Ref exploration (specific commits, branches, tags)
- File history and blame
- Time-travel queries (file@commit, file@tag)

Requires: pip install reveal-cli[git]
"""

from .adapter import GitAdapter

__all__ = ['GitAdapter']
