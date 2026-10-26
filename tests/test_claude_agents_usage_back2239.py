"""BACK-2239: claude://<session>/agents reads Claude Code's snake_case usage and the call's subagent_type."""
from claude_transcript_builder import (SESSION, assistant, install, prompt, run_json, tool_result,
                                       tool_use)

USAGE = {'input_tokens': 2, 'output_tokens': 977, 'cache_read_input_tokens': 25962,
         'cache_creation_input_tokens': 140, 'service_tier': 'standard'}


def _agent_session():
    return [
        prompt(0, 'review the thing'),
        assistant(1, [tool_use('a1', 'Agent', prompt='look around', subagent_type='general-purpose',
                               description='look')], 'm1'),
        tool_result(2, 'a1', 'done', toolUseResult={
            'status': 'completed', 'agentId': 'aaa111', 'agentType': 'Explore', 'prompt': 'look around',
            'totalDurationMs': 4200, 'totalTokens': 27081, 'totalToolUseCount': 6, 'usage': USAGE}),
        assistant(3, [tool_use('a2', 'Agent', prompt='background job', subagent_type='general-purpose',
                               run_in_background=True)], 'm2'),
        tool_result(4, 'a2', 'launched', toolUseResult={
            'status': 'async_launched', 'isAsync': True, 'agentId': 'bbb222', 'prompt': 'background job'}),
        assistant(5, [tool_use('a3', 'Agent', prompt='no type given')], 'm3'),
        tool_result(6, 'a3', 'launched', toolUseResult={
            'status': 'async_launched', 'isAsync': True, 'agentId': 'ccc333', 'prompt': 'no type given'}),
    ]


def test_agents_usage_is_read_from_snake_case_keys(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _agent_session())
    out = run_json(f'claude://session/{SESSION}/agents')
    foreground = out['agents'][0]
    assert foreground['usage'] == {'input_tokens': 2, 'output_tokens': 977,
                                   'cache_read_tokens': 25962, 'cache_created_tokens': 140}
    # negative control: the camelCase totals the same record carries were already right
    assert (foreground['agent_type'], foreground['duration_ms'], foreground['token_count'],
            foreground['tool_count']) == ('Explore', 4200, 27081, 6)
    assert out['total_agent_tokens'] == 27081 and out['total_agent_duration_ms'] == 4200


def test_background_agent_type_comes_from_the_call_input(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _agent_session())
    agents = run_json(f'claude://session/{SESSION}/agents')['agents']
    assert agents[1]['agent_type'] == 'general-purpose'
    assert agents[1]['status'] == 'async_launched'
    # negative control: a call that names no type anywhere is still 'unknown', and a launch
    # carries no telemetry to invent
    assert agents[2]['agent_type'] == 'unknown'
    assert 'usage' not in agents[1] and 'duration_ms' not in agents[1]


def test_workflow_view_gives_the_background_agent_the_same_type(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _agent_session())
    steps = run_json(f'claude://session/{SESSION}/workflow')['workflow']
    by_detail = {s['step']: s for s in steps if s['tool'] == 'Agent'}
    assert [s['agent_type'] for s in by_detail.values()] == ['Explore', 'general-purpose', 'unknown']
