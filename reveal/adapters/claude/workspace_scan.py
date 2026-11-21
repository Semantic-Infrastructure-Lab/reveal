"""Claude's workspace lists: the shared acquisition (``utils.workspace_scan``) and the list each answer holds."""
from functools import partial

from ...utils.workspace_scan import (WorkspaceScan, workspace_execution_facts, workspace_list_error,
                                     workspace_proof_error)

__all__ = ['WorkspaceScan', 'workspace_execution_facts', 'workspace_requirement_error', 'LIST_FIELDS']

_proof_error = partial(workspace_proof_error, label='Claude')

LIST_FIELDS = {'claude_plans': 'plans', 'claude_agents': 'agents',
               'claude_memory': 'memories', 'claude_hooks': 'hooks'}


def workspace_requirement_error(adapter, result, expected_type, prior_facts):
    count_key = 'displayed' if expected_type in ('claude_plans', 'claude_agents') else 'total'
    return workspace_list_error(adapter, result, LIST_FIELDS[expected_type], prior_facts, count_key=count_key,
                                label='Claude')
