"""BACK-1418: HTTP routes under their controller's prefix.

`surface` reported every ASP.NET / Spring action path without its
controller's class-level [Route] / @RequestMapping prefix (Jellyfin:
`Library/Folders/{id}` listed as `{id}`; petclinic's PetController routes
without `/owners/{ownerId}`). Stacked verb attributes were folded into the
last one seen ([HttpGet]+[HttpHead] -> HEAD gone), [AcceptVerbs] and
RequestMethod.X were ANY, a Spring path array was '?', and a prefix declared
on a base class in another file (26 of Jellyfin's 60 controllers) was never
applied.
"""

import textwrap
from pathlib import Path

import pytest

from reveal.adapters.ast.nav_surface_common import (
    INHERIT_KEY, ROUTE_CLASSES_KEY, join_route_path, merge_routes_by_path, resolve_inherited_route_prefixes,
)
from reveal.adapters.ast.nav_surface_csharp import scan_file_surface_csharp
from reveal.adapters.ast.nav_surface_java import scan_file_surface_java
from reveal.adapters.ast.nav_surface_kotlin import scan_file_surface_kotlin
from reveal.adapters.surface import _scan_surface

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding='utf-8')
    return str(path)


def _routes(result):
    return [(r['methods'], r['path'], r['name']) for r in result['http']]


def test_join_route_path():
    assert join_route_path(None, '/x') == '/x'
    assert join_route_path(None, None) is None
    assert join_route_path('/api/', '/x') == '/api/x'
    assert join_route_path('api', 'x') == 'api/x'
    assert join_route_path('api', None) == 'api'
    assert join_route_path('', 'x') == 'x'
    assert join_route_path('', None) == '/'


def test_merge_routes_by_path_joins_verbs_of_one_path():
    assert merge_routes_by_path([(['GET'], 'a'), (['HEAD'], 'a'), (['POST'], 'b')]) == [
        ('GET|HEAD', 'a'), ('POST', 'b'),
    ]
    assert merge_routes_by_path([(['ANY'], 'a')]) == [('ANY', 'a')]


def test_csharp_controller_prefix_stacked_verbs_accept_verbs(tmp_path):
    result = scan_file_surface_csharp(_write(tmp_path, 'C.cs', '''\
        [ApiController]
        [Route("Library/Folders")]
        public class FoldersController : ControllerBase
        {
            [HttpGet]
            public IActionResult List() => Ok();

            [HttpGet("{id}")]
            [HttpHead("{id}", Name = "HeadFolder")]
            public IActionResult Get(string id) => Ok();

            [Route("legacy/{id}")]
            [AcceptVerbs("GET", "POST")]
            public IActionResult Legacy(string id) => Ok();

            [HttpGet("/absolute")]
            public IActionResult Abs() => Ok();

            [HttpPost("a")]
            [HttpPut("b")]
            public IActionResult Two() => Ok();
        }
    '''))
    assert _routes(result) == [
        ('GET', 'Library/Folders', 'List'),
        ('GET|HEAD', 'Library/Folders/{id}', 'Get'),
        ('GET|POST', 'Library/Folders/legacy/{id}', 'Legacy'),
        ('GET', '/absolute', 'Abs'),
        ('POST', 'Library/Folders/a', 'Two'),
        ('PUT', 'Library/Folders/b', 'Two'),
    ]
    assert not any(INHERIT_KEY in r for r in result['http'])


def test_csharp_route_tokens_and_multiple_prefixes(tmp_path):
    result = scan_file_surface_csharp(_write(tmp_path, 'C.cs', '''\
        [Route("api/[controller]")]
        [Route("v2/[controller]")]
        public class ItemsController : ControllerBase
        {
            [HttpGet("[action]/{id}")]
            public IActionResult Find(string id) => Ok();
        }
    '''))
    assert _routes(result) == [
        ('GET', 'api/Items/Find/{id}', 'Find'),
        ('GET', 'v2/Items/Find/{id}', 'Find'),
    ]


def test_csharp_without_class_route_keeps_template_and_unknown_path(tmp_path):
    """No prefix anywhere: the template as written, '?' for a bare verb
    (conventional routing decides it)."""
    result = scan_file_surface_csharp(_write(tmp_path, 'C.cs', '''\
        public class UserController
        {
            [HttpGet("/users/{id}")]
            public string GetUser(string id) { return "x"; }

            [HttpPost]
            public void Create() {}
        }
    '''))
    assert _routes(result) == [('GET', '/users/{id}', 'GetUser'), ('POST', '?', 'Create')]


def test_java_class_request_mapping_arrays_and_request_method(tmp_path):
    result = scan_file_surface_java(_write(tmp_path, 'C.java', '''\
        @RestController
        @RequestMapping("/owners/{ownerId}")
        class PetController {
            @GetMapping("/pets/new") String a() { return ""; }
            @GetMapping({ "/x", "/y" }) String b() { return ""; }
            @RequestMapping(path = "/m", method = {RequestMethod.GET, RequestMethod.HEAD}) String m() { return ""; }
            @RequestMapping(value = "/s", method = RequestMethod.POST) String s() { return ""; }
            @PostMapping String p() { return ""; }
        }
    '''))
    assert _routes(result) == [
        ('GET', '/owners/{ownerId}/pets/new', 'a'),
        ('GET', '/owners/{ownerId}/x', 'b'),
        ('GET', '/owners/{ownerId}/y', 'b'),
        ('GET|HEAD', '/owners/{ownerId}/m', 'm'),
        ('POST', '/owners/{ownerId}/s', 's'),
        ('POST', '/owners/{ownerId}', 'p'),
    ]


def test_kotlin_class_request_mapping(tmp_path):
    result = scan_file_surface_kotlin(_write(tmp_path, 'C.kt', '''\
        @RestController
        @RequestMapping("/api")
        class C {
            @GetMapping(value = ["/a", "/b"]) fun a() {}
            @RequestMapping(path = ["/m"], method = [RequestMethod.GET, RequestMethod.HEAD]) fun m() {}
            @PostMapping fun p() {}
        }
        @RestController
        class D {
            @GetMapping("/plain") fun q() {}
        }
    '''))
    assert _routes(result) == [
        ('GET', '/api/a', 'a'), ('GET', '/api/b', 'a'), ('GET|HEAD', '/api/m', 'm'),
        ('POST', '/api', 'p'), ('GET', '/plain', 'q'),
    ]


@pytest.mark.parametrize("files, expected", [
    ({
        'Base.cs': '''\
            [ApiController]
            [Route("[controller]")]
            public class BaseApiController : ControllerBase {}
        ''',
        'Genres.cs': '''\
            public class GenresController : BaseApiController
            {
                [HttpGet] public IActionResult GetGenres() => Ok();
                [HttpGet("{genreName}")] public IActionResult GetGenre(string genreName) => Ok();
                [HttpGet("/abs")] public IActionResult Abs() => Ok();
            }
        ''',
        'Own.cs': '''\
            [Route("")]
            public class ItemsController : BaseApiController
            {
                [HttpGet("Items")] public IActionResult GetItems() => Ok();
            }
        ''',
    }, [
        ('GET', 'Genres', 'GetGenres'),
        ('GET', 'Genres/{genreName}', 'GetGenre'),
        ('GET', '/abs', 'Abs'),
        ('GET', 'Items', 'GetItems'),
    ]),
    ({
        'Base.java': '''\
            @RequestMapping("/api/v1")
            public abstract class BaseController {}
        ''',
        'Items.java': '''\
            @RestController
            public class ItemsController extends BaseController {
                @GetMapping("/items") public String list() { return ""; }
            }
        ''',
    }, [('GET', '/api/v1/items', 'list')]),
    ({
        'Api.kt': '''\
            @RequestMapping("/k")
            interface Api
            @RestController
            class Impl : Api {
                @GetMapping("/x") fun x() {}
            }
        ''',
    }, [('GET', '/k/x', 'x')]),
], ids=['csharp-base-class', 'java-superclass', 'kotlin-interface'])
def test_prefix_inherited_from_a_base_type_in_another_file(tmp_path, files, expected):
    for name, body in files.items():
        _write(tmp_path, name, body)
    http = _scan_surface(tmp_path)['surfaces']['http']
    assert sorted(_routes({'http': http})) == sorted(expected)
    assert not any(INHERIT_KEY in r for r in http)


def test_conflicting_same_named_bases_leave_the_path_unresolved():
    entry = {'path': 'x', INHERIT_KEY: {'class': 'C', 'action': 'a', 'tokens': False, 'template': 'x'}}
    http = [entry]
    resolve_inherited_route_prefixes(http, [
        {'name': 'C', 'prefixes': None, 'bases': ['B']},
        {'name': 'B', 'prefixes': ['/one'], 'bases': []},
        {'name': 'B', 'prefixes': ['/two'], 'bases': []},
    ])
    assert http == [{'path': 'x'}]


def test_scanner_class_records_only_when_classes_exist(tmp_path):
    assert ROUTE_CLASSES_KEY not in scan_file_surface_java(_write(tmp_path, 'E.java', 'package x;\n'))
