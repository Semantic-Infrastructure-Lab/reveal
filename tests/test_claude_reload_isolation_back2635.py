"""Environment reload tests cannot replace later fixtures' imported class identities."""
from claude_session_fixture import isolated_claude_reload


def test_reload_restores_module_and_registry_identity():
    import reveal.adapters.claude.adapter as module
    from reveal.adapters.registry import get_adapter_class
    original = module.ClaudeAdapter
    registered = get_adapter_class('claude')
    with isolated_claude_reload() as reload:
        reload()
        assert module.ClaudeAdapter is not original
        assert get_adapter_class('claude') is module.ClaudeAdapter
    assert module.ClaudeAdapter is original
    assert get_adapter_class('claude') is registered
