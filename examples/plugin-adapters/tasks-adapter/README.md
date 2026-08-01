# tasks:// — a worked example of a reveal plugin adapter

This is a reference example for reveal's **adapter plugin discovery**
mechanism (BACK-256, shipped in reveal 0.90.0+): a domain-specific `tasks://`
adapter, built and dropped into `.reveal/adapters/`, with zero changes to
reveal core and zero installation step.

Every adapter that ships inside reveal core (`ast://`, `git://`, `sqlite://`,
...) lives in `external-git/reveal/adapters/`. This example instead shows
what a *third party* building their own adapter for their own project looks
like — see `reveal/docs/development/ADAPTER_AUTHORING_GUIDE.md`'s "Writing
Adapters for External Projects" section for the mechanism itself; this
directory is the runnable example that section links to.

## What it does

`tasks://` reads a plain markdown+YAML task file — no dependency on any
particular task tracker, just a simple, generic format:

```markdown
## TASK-1: Fix the login timeout bug
```yaml
status: open
priority: high
```
Free-text description, until the next `## ` heading.
```

See [`TASKS.md`](TASKS.md) in this directory for a full sample file, and
[`.reveal/adapters/tasks/parser.py`](.reveal/adapters/tasks/parser.py) for
the parser.

## Try it

From *this directory* (the plugin only auto-loads when `.reveal/adapters/`
is under your current working directory):

```bash
cd examples/plugin-adapters/tasks-adapter

reveal 'tasks://TASKS.md'                  # list all tasks
reveal 'tasks://TASKS.md?status=open'      # filter by status
reveal 'tasks://TASKS.md?priority=high'    # filter by priority
reveal tasks://TASKS.md TASK-1             # a single task by id
reveal 'tasks://TASKS.md' --format json    # machine-readable output
reveal 'help://schemas/tasks'              # the adapter's own schema help
```

(If you're running against reveal's own dev tree instead of an installed
`reveal-cli`, prefix these with
`PYTHONPATH=/path/to/reveal/external-git`.)

## How the plugin is laid out

```
tasks-adapter/
  TASKS.md                          # sample data file to query
  .reveal/adapters/tasks/
    __init__.py                     # from .adapter import TasksAdapter
    adapter.py                      # @register_adapter('tasks')
    renderer.py                     # @register_renderer(TasksRenderer)
    parser.py                       # markdown+YAML -> list[dict] parsing
```

This mirrors the exact structure the discovery mechanism expects: reveal
scans `<cwd>/.reveal/adapters/` (and `~/.reveal/adapters/` for user-global
plugins) for package directories with an `__init__.py`, and imports each one
— the `@register_adapter`/`@register_renderer` decorators fire as a side
effect of that import, registering the scheme.

## The one thing that's different from a core adapter

Everything in `adapter.py`/`renderer.py`/`parser.py` is ordinary
`ResourceAdapter` subclassing, same as any adapter under
`external-git/reveal/adapters/`. The **only** required change for code living
outside the reveal package tree is importing from the *absolute* path:

```python
# Works only inside reveal core:
from ..base import ResourceAdapter, register_adapter, register_renderer

# Works anywhere reveal is installed (what this example uses):
from reveal.adapters.base import ResourceAdapter, register_adapter, register_renderer
```

Internal imports between the plugin's own files (`from .parser import
parse_tasks_file`) stay relative — those still work, since
`_load_adapter_plugin_dir` imports the package with `submodule_search_locations`
set to the plugin directory.

## Constructor convention — worth getting right

`ResourceAdapter.from_uri()` tries several constructor call shapes in order
until one works (see `reveal/adapters/factory.py`). For a `scheme://path?query`
adapter, the shape that's tried *first* — and the one this example uses — is:

```python
def __init__(self, path: str, query_string: Optional[str] = None):
    ...
```

`query_string` arrives as the raw, unparsed string after `?` (e.g.
`"status=open&priority=high"`); parse it yourself with
`urllib.parse.parse_qs`, as `adapter.py` does. A `**query_params`-style
signature looks tempting but isn't tried by the resolver the same way (query
params in a `?...` URI are passed as one positional string, not unpacked into
keyword args) — use the `path, query_string=None` shape shown here.

## Not scoped here

Whether this should also ship as its own installable PyPI package is
deliberately left open — this directory is meant to be the in-repo runnable
example (and the case study behind BACK-878); split it out only if real
third-party interest shows up.
