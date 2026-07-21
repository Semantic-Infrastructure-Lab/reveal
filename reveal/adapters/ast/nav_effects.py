"""Side-effect taxonomy classifier: collect_effects, render_effects."""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...core import node_children as _children
from ...core.treesitter_compat import _zero_arg
from .nav_calls import range_calls
from .node_taxonomy import MEMBER_ACCESS_NODES as _MEMBER_ACCESS_NODES

# Each entry: (kind_label, list_of_patterns).
#
# Matching model (BACK-283): patterns and callees are tokenized into segments
# on the delimiters `.`, `->`, `::`, and whitespace. A pattern matches if its
# segment sequence appears consecutively in the callee's segment sequence
# (sliding-window equality, case-insensitive). This is segment-boundary
# matching, not substring containment, so `header` no longer matches
# `printHeader` and `mail` no longer matches `gmail`.
#
# Order matters — first match wins.
#
# BACK-431 Issue D: patterns that are only meaningful for one language/runtime
# (a builtin function name, a stdlib module path) live in _TAXONOMY_BY_LANG,
# keyed by the analyzer's `language` attribute (aliased via _LANG_GROUP for
# JS/TS variants). Patterns with no single-language home (generic verbs like
# `db_query`, receiver-shape callees like `->execute`) stay in _TAXONOMY_COMMON
# and apply everywhere. classify_call()/collect_effects() take an optional
# `language` — when given, only common + that language's patterns are checked,
# so (e.g.) a Go file can no longer be tagged 'session' by a PHP builtin named
# `session_start`. When omitted, behavior is unchanged from before this split:
# common + every language's patterns are checked (see _COMPILED_ALL).
_TAXONOMY_COMMON: List[Tuple[str, List[str]]] = [
    ('hard_stop', [
        'die', 'exit', 'abort', 'halt',
    ]),
    ('db', [
        'pg_query', 'pg_fetch', 'sqlite_query',
        # BACK-635: `->update`/`->delete` were removed from the COMMON table and
        # moved to PHP-only (_TAXONOMY_BY_LANG['php']). The tokenizer strips the
        # `->`/`::` sigil, so these arrow patterns collapse to the collision-prone
        # BARE verbs `update`/`delete` — which then wrongly matched any language's
        # ordinary `dict.update()` / `list`-ish `.update()` (corpus: 12 db FPs on
        # Home Assistant, incl. 2/60 negative-control FPs) and stole Python's
        # `requests.delete(url)` from http (kind-order db<http let bare `delete`
        # win over the explicit python `requests.delete`->http). `->fetch` was
        # REMOVED (TS sideeffects-recall-oracle pre-flight check, BACK-547 fifth
        # loop): its bare form ('fetch') collided with JS/TS's global `fetch()`
        # — the dominant modern HTTP call idiom — stealing it from the
        # js-language http bucket's own explicit 'fetch(' entry, since db
        # precedes http in _KIND_ORDER. Confirmed via corpus grep (samples/python)
        # that bare `.fetch(` has zero real occurrences in Python — only PHP's
        # `$stmt->fetch()` needs it (see _TAXONOMY_BY_LANG['php']).
        #
        # BACK-636/BACK-633: `->query`/`->execute`/`->select`/`->insert` also
        # moved out of COMMON to python+php-only (same shape as the update/delete
        # move above). Corpus-wide grep (samples/, full trees not just the
        # original single-subtree findings) showed these bare verbs are NOT
        # collision-safe: `.execute(` has 8,301 Java call sites (dominant idiom
        # is `java.util.concurrent.Executor.execute`, not db — corpus-confirmed
        # on Elasticsearch's `clusterCoordinationExecutor.execute(...)`), `.select`
        # has 980 Ruby call sites (dominant idiom is `Enumerable#select`, corpus-
        # confirmed on Discourse), `->insert(` has 70 C++ STL-container sites
        # (`HashMap::insert`/`Vector::insert`, corpus-confirmed on Godot) and
        # `.Insert(` has 1,210 Go sites (corpus-confirmed on client-go). Recall
        # is preserved: python/php get these verbs back via their own
        # per-language tables below (python's `cursor.execute`/`session.query`,
        # php's `$stmt->execute()`/`DB::table(...)->insert(...)`), the two
        # languages the original comment identified these bare forms as
        # load-bearing for.
        'db_query', 'db_insert', 'db_update', 'db_delete',
    ]),
    ('http', [
        'http_get', 'http_post',
        # Re-added 2026-05-05 (BACK-283): segment-boundary matching makes
        # bare 'header' safe — it no longer matches user wrappers like
        # 'printHeader' or 'request_headers'.
        'header',
    ]),
    ('cache', [
        'redis->', 'redis::',
        'cache.get', 'cache.set', 'cache.delete',
    ]),
    ('file', [
        'fopen', 'fwrite', 'fread', 'fclose', 'fputs',
        # BACK-635: bare `copy` moved to PHP-only (PHP's `copy($src,$dst)`
        # builtin). As a bare, undotted verb it matched every language's ordinary
        # value-copy idiom — `dict.copy()`, `x.copy()`, `os.environ.copy()`
        # (corpus: 4 file FPs on Home Assistant) — none of which is filesystem
        # I/O. `rename`/`unlink`/`mkdir`/`rmdir` stay: they have negligible
        # non-file collision risk (values don't carry `.rename()`/`.unlink()`
        # methods) and produced no corpus FPs.
        'rename', 'unlink', 'mkdir', 'rmdir',
        'readfile', 'tmpfile', 'open(',
    ]),
    ('env', [
        'getenv', 'putenv',
    ]),
    ('log', [
        'syslog', 'write_log', 'logger.', 'log.', 'app.logger',
    ]),
    ('sleep', [
        'sleep', 'usleep',
    ]),
]

_TAXONOMY_BY_LANG: Dict[str, List[Tuple[str, List[str]]]] = {
    'php': [
        ('db', [
            'mysql_query', 'mysql_fetch', 'mysqli_query', 'mysqli_fetch',
            'wpdb', '$wpdb', 'pdo->', 'pdo::', 'new pdo',
            # BACK-635: moved here from _TAXONOMY_COMMON. `$obj->update(...)` /
            # `$obj->delete(...)` are legitimate PHP ActiveRecord/query-builder
            # db idioms, but as bare verbs they over-fired on other languages'
            # `.update()`/`.delete()` — so they are now PHP-scoped. (In unscoped
            # `_COMPILED_ALL` mode every language's patterns merge, so this move
            # is behavior-preserving there; it only tightens the per-language
            # scoped tables.)
            '->update', '->delete',
            # Moved from _TAXONOMY_COMMON (TS sideeffects-recall-oracle,
            # BACK-547 fifth loop): bare 'fetch' collided with JS/TS's global
            # `fetch()` HTTP call. PHP's `$stmt->fetch()` (PDOStatement/
            # mysqli_result row fetch) is the only real, corpus-confirmed user.
            '->fetch',
            # BACK-636/BACK-633: moved here from _TAXONOMY_COMMON, same shape
            # as the ->update/->delete move above. `$pdo->query()`/
            # `$stmt->execute()` (raw PDO) and Laravel's fluent query builder
            # (`DB::table(...)->select(...)`, `->insert(...)`) are the real PHP
            # users; as bare verbs they over-fired elsewhere (see COMMON's db
            # bucket comment for the corpus numbers: Java .execute, Ruby
            # .select, C++/Go .insert).
            '->query', '->execute', '->select', '->insert',
            '::query', '::execute',
        ]),
        ('http', [
            'curl_exec', 'curl_setopt', 'curl_init',
            'file_get_contents',
            'wp_remote_get', 'wp_remote_post', 'wp_remote_request',
            'setcookie', 'setrawcookie', 'mail',
            # BACK-649 (sideeffects-recall-oracle/php, seventh language):
            # raw-socket HTTP idiom used by hand-rolled protocol clients
            # (POP3, FTP, WP_Http's streams transport) predating cURL/
            # wp_remote_*. Real miss: class-pop3.php:connect ->
            # `fsockopen("$server", $port, ...)`. Bare stdlib builtin, no
            # corpus redefinitions, negligible collision risk.
            'fsockopen',
        ]),
        ('cache', [
            'memcache_get', 'memcache_set', 'memcache_delete', 'memcache_add',
            'apc_store', 'apcu_store', 'apcu_fetch',
            'apc_fetch', 'apc_delete', 'apcu_delete',
            'wp_cache_get', 'wp_cache_set', 'wp_cache_delete',
        ]),
        ('session', [
            'session_start', 'session_destroy', 'session_regenerate_id',
            'session_unset', 'session_write_close', 'session_id',
        ]),
        ('file', [
            'file_put_contents', 'file_get_contents',
            # BACK-635: PHP's `copy($src, $dst)` filesystem builtin — moved here
            # from _TAXONOMY_COMMON, where the bare verb wrongly matched every
            # language's value-copy `.copy()` (dict/list/os.environ).
            'copy',
        ]),
        ('log', [
            'error_log', 'trigger_error', 'var_dump', 'phpinfo',
            # BACK-649 (sideeffects-recall-oracle/php, seventh language):
            # error_reporting() reads/sets PHP's runtime error-diagnostic
            # level -- real corpus misses: load.php:wp_debug_mode,
            # class-wpdb.php:check_connection,
            # class-wp-http-streams.php:request,
            # class-wp-customize-selective-refresh.php:handle_render_partials_request.
            # Bare stdlib builtin, no corpus redefinitions.
            'error_reporting',
        ]),
    ],
    'python': [
        ('hard_stop', ['sys.exit', 'os._exit']),
        # BACK-594: SQLAlchemy ORM operations on a `session` receiver. These
        # replace the language-UNSCOPED `session`/`connection` -> db receiver
        # heuristic that was dropped from _RECEIVER_TAXONOMY (it tagged aiohttp
        # `session.get(url)` / OAuth `session.async_ensure_token_valid()` /
        # websocket `connection.send_result(...)` as db — `session`/`connection`
        # are extremely common non-db variable names). Each verb here is an
        # unambiguous SQLAlchemy Session method with no aiohttp/websocket
        # counterpart (aiohttp ClientSession has none of add/flush/commit/…),
        # so it classifies the real db call without the cross-domain FP.
        # `session.query`/`session.execute` are caught by the bare 'query'/
        # 'execute' patterns below; `session.get`/`session.delete` are
        # deliberately OMITTED — they are genuinely ambiguous (SQLAlchemy 2.0
        # db read vs aiohttp http verb), so per the conservative philosophy we
        # DECLINE.
        ('db', [
            'session.add', 'session.add_all', 'session.flush', 'session.commit',
            'session.rollback', 'session.refresh', 'session.expunge',
            'session.expunge_all', 'session.merge', 'session.connection',
            'session.scalar', 'session.scalars',
            # BACK-636/BACK-633: moved here from _TAXONOMY_COMMON's db bucket.
            # Bare 'query'/'execute'/'select'/'insert' are load-bearing for
            # Python DB-API/SQLAlchemy recall (`cursor.execute`,
            # `session.query`, SQLAlchemy Core's `select(...)`/`insert(...)`
            # constructs) but over-fired cross-language when common (see
            # COMMON's db bucket comment for corpus numbers). Scoping here is
            # behavior-preserving for Python: these bare forms already applied
            # to Python under the old unscoped-common table, including the
            # pre-existing `list.insert()`/`iterable.select()`-shaped FPs that
            # existed before this move too — not a new regression, just now
            # contained to python+php instead of every language.
            'query', 'execute', 'select', 'insert',
        ]),
        ('http', [
            'requests.get', 'requests.post', 'requests.put', 'requests.delete',
            'urllib.request', 'httpx.', 'aiohttp.',
        ]),
        ('file', [
            'os.rename', 'os.unlink', 'os.mkdir', 'shutil.',
            # BACK-634 (sideeffects-recall-oracle/python, real-corpus
            # measurement on Home Assistant): os.remove / os.makedirs are the
            # exact stdlib twins of the already-present os.unlink / os.mkdir
            # (os.remove == unlink for files, os.makedirs == recursive mkdir)
            # and were silently unclassified — os.remove is the single most
            # common file-deletion idiom in the corpus. Real misses:
            # `os.remove(filename)` (nest/media_source.py:async_remove_media,
            # verisure/camera.py:delete_image), `os.makedirs(...)`
            # (helpers/storage.py:_write_prepared_data, knx/telegrams.py).
            # Dotted `os.` prefix => zero collision risk.
            'os.remove', 'os.makedirs',
            # 'pathlib' (module) stays; the bare 'Path(' constructor pattern
            # was removed (BACK-416) — it tokenizes to just ['path'] and so
            # matched any segment named `path` (e.g. a local var in
            # `path.resolveIndex()`), and constructing a Path is not itself a
            # filesystem side effect anyway.
            'pathlib',
            # BACK-634: pathlib's file-I/O methods are invoked on Path *values*
            # (`self._path.write_text(...)`, `file_path.read_bytes()`), so the
            # 'pathlib' module pattern never sees them — the receiver is a local
            # var, not the `pathlib` module. These four method names are
            # pathlib-specific I/O verbs with negligible non-file collision risk
            # — the exact same shape BACK-477 added for Kotlin's kotlin.io
            # (writeText/readText/writeBytes/readBytes). Real misses:
            # `self._path.write_text(ics_content)` (local_calendar/store.py),
            # `file_path.read_bytes()` (llama_cpp/entity.py). mkdir/unlink are
            # already bare in _TAXONOMY_COMMON, so Path.mkdir()/Path.unlink()
            # were already caught.
            'write_text', 'read_text', 'write_bytes', 'read_bytes',
        ]),
        ('env', ['os.environ', 'os.getenv']),
        ('log', ['logging.']),
        ('sleep', ['time.sleep', 'asyncio.sleep', 'gevent.sleep']),
    ],
    'js': [
        # BACK-547 (sideeffects-recall-oracle, fifth loop, real-corpus
        # measurement on VS Code's src/vs + extensions, 65,008 functions):
        # this bucket previously had ZERO db/file/env entries — only http/
        # log/sleep — despite js/ts being the language most-tested by the
        # program's own dogfooding (never actually corpus-validated before).
        ('db', [
            # Browser IndexedDB API — the dominant client-side db idiom with
            # no server/db process. Real miss: `indexedDB.deleteDatabase(...)`
            # (src/vs/base/browser/indexedDB.ts:deleteDatabase). Dotted /
            # specific-verb forms => negligible collision risk.
            'indexeddb.open', 'indexeddb.deletedatabase', 'createobjectstore',
        ]),
        ('http', [
            'fetch(',
            # Node stdlib http/https modules — real miss: `https.get(...)`
            # (extensions/vscode-test-resolver/src/download.ts:
            # downloadVSCodeServerArchive). Dotted => zero collision risk.
            # NOT added: VS Code's own `requestService.request(...)`
            # wrapper (3 real misses) — a single-repo internal abstraction
            # name, same declined shape as the Python loop's
            # `async_get_clientsession` (BACK-634) and Go's `client.Do`
            # (BACK-633): not a public stdlib/ecosystem idiom, belongs in
            # `.reveal.yaml` project-scoping (BACK-238) if ever addressed.
            'http.get', 'http.request', 'https.get', 'https.request',
        ]),
        ('log', ['console.log', 'console.error', 'console.warn']),
        ('sleep', ['setTimeout', 'setInterval']),
        # NO env bucket, deliberately (BACK-644, fixed): Node's dominant
        # env-read idiom is `process.env.FOO` / `process.env['FOO']` — a plain
        # property/index READ, not a call. classify_call() only ever sees callee
        # text from range_calls()'s call_expression extraction (nav_calls.py),
        # so no *call*-taxonomy pattern can classify this shape; an
        # ('env', ['process.env']) entry here would be dead code (verified:
        # 0/26 real corpus hits with the pattern present). JS/TS env reads ARE
        # classified now — by collect_effects()'s separate property channel
        # (_ENV_BASES_BY_LANG below), not from this table.
    ],
    'go': [
        ('file', [
            'os.open', 'os.openfile', 'os.create', 'os.remove', 'os.mkdirall',
            'ioutil.readfile', 'ioutil.writefile',
        ]),
        # BACK-629 (sideeffects-recall-oracle, real-corpus measurement on
        # k8s.io/client-go): Go had NO http bucket at all — every idiomatic
        # net/http call (`http.Get`, `.RoundTrip(req)` on an http.RoundTripper,
        # the dominant transport-layer idiom in client-go) was silently
        # unclassified. `http_get`/`http_post` in _TAXONOMY_COMMON are
        # snake_case literals (tokenize to one segment, `['http_get']`) and so
        # never matched Go's dotted `http.Get(` (`['http', 'get']`) — a
        # segment-count mismatch, not a missing verb. 'roundtrip' is bare
        # (matches any receiver, e.g. `rt.RoundTrip(req)`, `transport.RoundTrip`)
        # since RoundTripper is the canonical Go net/http transport interface
        # method name and not collision-prone with unrelated domain verbs.
        ('http', [
            'http.get', 'http.post', 'http.head', 'http.postform',
            'http.newrequest', 'http.newrequestwithcontext',
            'roundtrip',
        ]),
        # BACK-629: klog (k8s.io/klog, the dominant structured logger across
        # the entire Kubernetes ecosystem) and glog/logrus were silently
        # unclassified — the common bare 'log' pattern only matches a segment
        # that is EXACTLY 'log' (e.g. Go stdlib `log.Println`), and 'klog' is
        # a distinct token, not a substring match, under segment-boundary
        # tokenization. Real miss: `klog.Fatalf(...)` in client-go's azure
        # auth plugin `init()` was unclassified before this fix.
        ('log', ['klog', 'glog', 'logrus']),
        # BACK-629: `os.LookupEnv` (the idiomatic Go form for an optional env
        # read, used throughout client-go's feature-gate machinery) had no
        # pattern at all — only bare 'getenv'/'putenv' exist in
        # _TAXONOMY_COMMON, and 'lookupenv' is a distinct token. Real miss:
        # `os.LookupEnv(...)` in client-go's `envvar.go` feature-gate reader
        # was unclassified before this fix. `os.Setenv`/`os.Unsetenv`/
        # `os.Environ` added for the same reason (all in `os`, none matched).
        ('env', ['os.lookupenv', 'os.setenv', 'os.unsetenv', 'os.environ']),
    ],
    'rust': [
        ('hard_stop', ['std::process::exit']),
        ('file', ['std::fs']),
        ('env', [
            'std::env',
            # BACK-547 ninth loop: `use std::env;` then bare `env::var(...)`/
            # `env::var_os(...)` is the idiomatic form once imported (milli
            # corpus: env_var_or in vector/store.rs) -- the fully-qualified
            # `std::env` entry above never matches this since the `std`
            # segment is absent. 'env::' scoped to rust is unambiguous (not
            # a generic English word like 'debug'/'error' below).
            'env::var', 'env::var_os', 'env::set_var', 'env::remove_var',
        ]),
        # BACK-547 ninth loop: heed (LMDB binding, this corpus's dominant
        # db layer) transactions are acquired via `.read_txn()`/
        # `.write_txn()` -- often the ONLY db-shaped call in a function
        # whose real database access happens through an opaque already-open
        # `&rtxn` parameter with no further textual signal. Not in
        # _TAXONOMY_COMMON at all (no prior language needed them).
        # Deliberately does NOT include a bare `.commit` entry: since
        # per-language tables are merged into BOTH the scoped `rust` table
        # AND the fully-unscoped `_COMPILED_ALL` table (there is no
        # "visible only when scoped" tier), a bare `.commit` pattern
        # regressed the existing BACK-594 `conn`/`connection` precedent
        # live in this loop's own test run --
        # `classify_call('conn.commit')` (unscoped) started returning 'db'
        # again, the same cross-language receiver-name collision BACK-594
        # already declined. `RwTxn`/`RoTxn` are TYPE annotations, never
        # callee text, so a bare-name pattern for them could never actually
        # match anyway. `read_txn`/`write_txn` are safe: compound,
        # heed-specific method names with no found collision.
        ('db', ['read_txn', 'write_txn']),
        # BACK-547 ninth loop (sideeffects-recall-oracle/rust, real-corpus
        # measurement on Meilisearch's milli engine): Rust logging is done
        # almost exclusively via the `tracing`/`log` crates' macros
        # (`tracing::debug!(...)`, or bare `debug!(...)` after a `use
        # tracing::debug` import) -- these were the dominant 'log' miss
        # category once BACK-547's companion fix (macro_invocation added to
        # CALL_NODE_TYPES) made the calls visible at all. Scoped to 'rust'
        # (not common) because bare 'info'/'warn'/'error'/'debug'/'trace'
        # are generic English words with real non-log collision risk in
        # other languages (e.g. Python's `logging.info` already covered by
        # the common `log.` prefix pattern; a bare unscoped 'error' would
        # falsely tag ordinary error-handling calls named `.error()`
        # unrelated to logging).
        ('log', [
            'tracing::info', 'tracing::warn', 'tracing::error',
            'tracing::debug', 'tracing::trace',
            'log::info', 'log::warn', 'log::error', 'log::debug', 'log::trace',
        ]),
    ],
    'java': [
        # BACK-639 (sideeffects-recall-oracle/java, real-corpus measurement on
        # Elasticsearch server): `System.getProperty` is Java's dominant
        # env-config-read idiom (JVM system properties, e.g. `-Des.foo=bar`)
        # and was entirely unclassified — 12/13 real env misses in the
        # stratified sample traced to it (`System.getProperty("es.logs.base_path")`
        # in bootstrap/Bootstrap.java, `System.getProperty("es.index.max_number_of_shards", ...)`
        # in IndexMetadata.java, and 10 more). Dotted `system.` prefix => zero
        # collision risk, same shape as the existing `system.getenv` entry.
        ('env', ['system.getenv', 'system.getproperty']),
    ],
    # BACK-477: Kotlin's kotlin.io File extension functions — none of these
    # match any existing pattern (verified: 'writeText'/'appendText'/etc are
    # single camelCase tokens, tokenizing to e.g. 'writetext', not 'write').
    'kotlin': [
        ('file', [
            'writetext', 'appendtext', 'readtext',
            'writebytes', 'appendbytes', 'readbytes',
            'copyto', 'deleterecursively', 'mkdirs', 'createnewfile',
        ]),
        # BACK-547 (sideeffects-recall-oracle/kotlin, tenth language): SQLDelight's
        # query-execution/transaction idiom is a single camelCase token
        # ('executeAsOne' etc.) — same tokenizer gap as C#'s 'savechangesasync'
        # (BACK-547 8th loop, eighth language). Corpus (Tivi's data/ module, 252
        # files): 68 executeAs*() calls + 4 transactionWithResult() calls across
        # 17 files, 0 unclassified before this fix.
        ('db', [
            'executeasone', 'executeaslist', 'executeasoneornull',
            'transactionwithresult',
        ]),
    ],
    # BACK-477: Swift's dominant file-write idiom is `"...".write(toFile:...)`
    # / `data.write(to: url)` — the argument label carrying the file-specific
    # meaning isn't visible to classify_call (callee text only), but a bare
    # `write` callee is Swift-specific enough here (scoped via `language`) to
    # not collide with other 'write' meanings the way an unscoped common
    # pattern would.
    'swift': [
        # BACK-547 Swift sideeffects-recall-oracle (eleventh/final language):
        # Apollo GraphQL's `client.fetch(query:)` / `client.perform(mutation:)`
        # (plus the completion-handler/async overloads `fetchWithResult` /
        # `performWithResult`) are the dominant network idiom in Kickstarter's
        # KsApi service layer — 100+ call sites across Service.swift and its
        # ApolloClient extensions, all unclassified before this fix. The
        # tokenizer doesn't split camelCase (same shape as C#'s
        # `SaveChangesAsync`), so `fetchwithresult`/`performwithresult` need
        # their own entries alongside the bare `fetch`/`perform` forms.
        # Receiver names vary too much (apiService/client/asyncClient/
        # sharedClient/self) for a receiver-suffix mechanism, so this is a
        # bare-verb bucket entry instead — scoped to `swift` only, so it can
        # never fire for Ruby's unrelated `reviewable.perform(...)` (Discourse
        # action dispatch, 230 corpus hits) or similar per-language verbs.
        # Corpus-wide collision check (samples/swift, all 5,327 files): the
        # only non-network `.perform(` is a local, project-specific
        # `UIView.perform(animated:closure:)` static helper (2 call sites in
        # one file) — accepted, same conservative trade-off as Kotlin's
        # declined `Store` receiver but inverted: here the network reading
        # overwhelmingly dominates (65+ sites) rather than the reverse.
        # `dataTask` (URLSession's raw completion-handler API, NSURLSession.swift)
        # is rarer (3 corpus hits) but unambiguous.
        ('http', ['fetch', 'perform', 'fetchwithresult', 'performwithresult', 'datatask']),
        ('file', ['write']),
        # BACK-498 quick win: NSLog/os_log are Swift/Cocoa's logging calls —
        # bare `print` deliberately stays unclassified (matches tier1 Java/C#/
        # Python treatment of stdout writes as non-log), but NSLog/os_log are
        # unambiguous logging APIs, not print wrappers.
        ('log', ['nslog', 'os_log']),
    ],
    # csharp/ruby/cpp: --sideeffects/--boundary classify_call() was never
    # actually gated to Python/TS (the docs claiming that were stale — these
    # three already worked via _TAXONOMY_COMMON alone); this adds their
    # dominant per-language idioms for parity with the other 8 languages that
    # already have a dedicated bucket (php/python/js/go/rust/java/kotlin/swift).
    'csharp': [
        ('db', [
            'executereader', 'executenonquery', 'executescalar', 'savechanges',
            # BACK-547 C# sideeffects-recall-oracle (eighth language): the
            # tokenizer doesn't split camelCase, so 'savechanges' never
            # matched EF Core's async overload as its own segment. Dominant
            # real corpus miss: 10/15 pre-fix recall misses, all
            # `await dbContext.SaveChangesAsync(...)` -- the standard EF
            # Core save idiom used throughout Jellyfin's repository layer
            # (DeviceManager, UserManager, KeyframeRepository,
            # ChapterRepository, and 3 migration routines). 37 corpus
            # occurrences across 16 files, 0 non-EF collisions found.
            'savechangesasync',
        ]),
        ('http', [
            'getasync', 'postasync', 'putasync', 'deleteasync', 'sendasync',
        ]),
        ('file', [
            'writealltext', 'readalltext', 'writealllines', 'readalllines',
            'createdirectory', 'streamwriter', 'filestream',
            # BACK-547 C# recall-oracle: StreamReader is StreamWriter's
            # equally-common read-side counterpart (already listed above)
            # but was entirely absent. Real corpus misses:
            # EncodedRecorder.StartStreamingLog, M3uParser.Parse (both
            # `new StreamReader(...)`).
            'streamreader',
        ]),
        ('env', ['getenvironmentvariable']),
        ('log', [
            'loginformation', 'logerror', 'logwarning', 'logdebug', 'logcritical',
        ]),
        # 'task.delay' kept 2-segment (not bare 'delay') to avoid colliding
        # with unrelated domain uses of a generic word like a UI/animation delay.
        ('sleep', ['task.delay']),
    ],
    'ruby': [
        ('file', [
            'file.write', 'file.read', 'file.delete',
            'fileutils.rm', 'fileutils.mkdir_p',
            # BACK-547 sixth loop (Ruby sideeffects-recall-oracle, Discourse
            # corpus): 'rm_f'/'rm_rf' are distinct tokens from 'rm' under
            # segment-boundary matching (`FileUtils.rm_rf(...)` doesn't
            # contain 'rm' as its own segment). Real corpus misses:
            # lib/socket_server.rb:stop, lib/directory_helper.rb:remove_tmp_directory.
            'fileutils.rm_f', 'fileutils.rm_rf',
        ]),
        ('db', [
            # BACK-547 sixth loop: ActiveRecord CRUD/query verbs, previously
            # declined here as "too collision-prone" without corpus evidence.
            # Measured instead: Discourse's real `.where(`/`.pluck(`/
            # `.find_by(`/`.update_all(`/`.delete_all(`/`.destroy_all(` call
            # sites are overwhelmingly on Model-constant or relation-shaped
            # receivers (`User.where`, `posts.where`, `scope.pluck`, ...);
            # grepping the whole corpus for a custom `def where`/`def pluck`/
            # `def update_all`/`def delete_all`/`def destroy_all` found only
            # 4 total, all themselves DB/cache-adjacent helpers (a preloader
            # shim, a cached-view class) — no unrelated-domain collision
            # found. Oracle recall on this bucket: 13.5% -> majority of the
            # remaining db miss category once these land (37 oracle db
            # instances in the sample, only 5 hit pre-fix).
            'where', 'pluck', 'find_by', 'find_by!',
            'update_all', 'delete_all', 'destroy_all',
            # Raw `pg` gem usage (bypassing ActiveRecord entirely) -- corpus:
            # 8 real occurrences, all `PG.connect(...)` (import/migration
            # tooling that opens its own connection). Dotted two-segment
            # pattern, negligible collision risk.
            'pg.connect',
        ]),
        ('http', [
            'net::http', 'httparty', 'faraday',
            # BACK-547 sixth loop: 'net::http' alone only matched
            # `Net::HTTP.get`/`.post`/`.start`-shaped calls; real corpus
            # traffic also constructs a request object directly
            # (`Net::HTTP::Post.new(uri)`) before `.request(...)`-ing it on an
            # instance -- the instance `.request(` call itself stays
            # unclassified (same collision-prone bare-verb shape as Go's
            # `client.Do`, deliberately declined), but the construction step
            # is real signal and corpus-safe (`Net::HTTP::Get`/`Post`/`Put`/
            # `Delete`/`Head` are not generic class names).
            'net::http::get', 'net::http::post', 'net::http::put',
            'net::http::delete', 'net::http::head',
        ]),
    ],
    'c': [
        # BACK-718/BACK-721 (sideeffects-recall-oracle loop, Redis `src/`
        # corpus): plain C has no dotted-receiver syntax, so classify_call()'s
        # segment-subsequence matching can only ever equal a bare call's
        # WHOLE fused identifier as one token -- there is no prefix/suffix
        # matching for camelCase-fused names (same limitation noted for C#'s
        # SaveChangesAsync/Kotlin's executeAsOne). C had zero language-scoped
        # entries before this loop (fell back to _TAXONOMY_COMMON only), and
        # _TAXONOMY_COMMON's generic verbs never matched any of Redis's three
        # dominant idioms below -- pre-fix corpus recall was 41.03% (log 0%,
        # http 0%, file 50%).
        #
        # log: serverLog/serverLogRaw (server.c) is the project's own
        # structured-logging wrapper around vsnprintf+write, used at 800+
        # call sites -- the single largest miss in the corpus (log 0%->near
        # total). serverPanic/_serverAssert/serverAssertWithInfo are the
        # fatal-error counterparts (also log a message before aborting).
        ('log', [
            'serverlog', 'serverlograw', 'serverpanic',
            '_serverassert', 'serverassertwithinfo',
        ]),
        # http: Redis has no HTTP client/server (it IS a database) -- the
        # corpus's real network boundary is the POSIX socket API, wrapped by
        # its own `anet*` helpers (anet.c). Only the anet* compound names are
        # added: bare 'connect'/'accept'/'listen'/'socket'/'send'/'recv' were
        # tried first and REVERTED after scripts/check_taxonomy_collisions.py
        # (run against every language's real corpus, not just C's) found they
        # are catastrophically overloaded generic English verbs elsewhere --
        # 'accept' alone hits 3,947 Java call sites, 'connect' 3,557 C++ and
        # 194 Go, 'send' hits every language from Swift to Ruby -- and two
        # existing hard invariants broke in _COMPILED_ALL (unscoped) mode:
        # `engine.connect` silently stopped classifying as 'db' (the existing
        # _RECEIVER_TAXONOMY fallback never got a chance to run once a verb
        # match short-circuited it) and `mailer.send` started wrongly
        # classifying as 'http'. Plain C's lack of receiver/dot syntax means
        # there is no way to scope these six verbs narrower than "the whole
        # call", so -- like Go's declined bare `Do` and C++'s declined bare
        # `Do`-shaped verbs -- they are declined outright rather than fixed.
        # The residual http miss this leaves (raw POSIX accept/connect/send/
        # recv calls not wrapped by an anet* helper) is real and open.
        ('http', ['anettcpconnect', 'anetunixconnect', 'anettcpgenericconnect']),
        # file: fopen/fwrite/fread/fclose (_TAXONOMY_COMMON) already cover
        # Redis's plain stdio use, but its RDB/AOF persistence subsystem is
        # built on its own `rio` (redis I/O) abstraction (rio.c) -- rioWrite/
        # rioRead and the rioWriteBulk* family are the actual byte-level
        # primitives; rdbWriteRaw (rdb.c) is the one-hop wrapper every
        # rdbSave*() helper bottoms out through. (rdbSave*/rdbLoad* themselves
        # were deliberately NOT added: they're a multi-level call chain
        # calling each other, not a flat idiom family, and reveal only
        # classifies direct calls -- adding the whole family would just move
        # the miss one level down, not fix it. See the oracle's
        # build_oracle.py for the corpus evidence this was checked against.)
        # fflush is a standard C stdio primitive missing from
        # _TAXONOMY_COMMON's file bucket entirely (only fopen/fwrite/fread/
        # fclose/fputs are listed) -- real corpus misses: rio.c's
        # rioFileFlush() wraps it directly, and redis-cli.c's interactive
        # output path calls it 5+ times. Scoped to 'c' rather than promoted
        # to common, matching this loop's discipline of only fixing what the
        # corpus confirmed (same choice Go's loop made for os.Setenv/
        # os.Environ rather than generalizing to _TAXONOMY_COMMON).
        ('file', [
            'riowrite', 'rioread', 'rdbwriteraw', 'fflush',
            'riowritebulkcount', 'riowritebulkstring',
            'riowritebulklonglong', 'riowritebulkdouble',
        ]),
        # setenv/unsetenv: same gap as Go's os.Setenv/os.Unsetenv miss
        # (BACK-629) -- _TAXONOMY_COMMON only has bare getenv/putenv. Real
        # miss: setproctitle.c's spt_copyenv() calls setenv() directly while
        # rebuilding the environment array after clearenv().
        ('env', ['setenv', 'unsetenv']),
        # nanosleep: _TAXONOMY_COMMON's sleep bucket only has 'sleep'/
        # 'usleep' -- POSIX's higher-resolution nanosleep() (used by
        # `debug sleep` in debug.c) was unclassified.
        ('sleep', ['nanosleep']),
    ],
    'cpp': [
        # BACK-547 fourth language (C++ sideeffects-recall-oracle loop,
        # Godot engine `core/` corpus): 'ofstream'/'ifstream'/etc. above are
        # generic-stdlib C++ file I/O, but a codebase built on a
        # cross-platform engine abstraction almost never calls them
        # directly — `FileAccess::open`/`->store_*`/`->get_*` is the idiom
        # actually used (verified: every real `get_buffer`/`store_buffer`
        # call site across core/servers/drivers is on a FileAccess-derived
        # receiver, no collision found). 'fileaccess' catches the static
        # factory (`FileAccess::open(...)`); the verbs catch instance calls.
        ('file', [
            'ofstream', 'ifstream', 'fstream', 'freopen',
            'fileaccess', 'diraccess',
            'store_line', 'store_string', 'store_buffer',
            'store_8', 'store_16', 'store_32', 'store_64',
            'get_as_text', 'get_buffer',
        ]),
        ('http', [
            'curl_easy_perform', 'curl_easy_setopt', 'curl_easy_init',
        ]),
        # bare 'sleep'/'exit'/'abort'/'getenv' already covered by
        # _TAXONOMY_COMMON; 'sleep_for' (std::this_thread::sleep_for) is the
        # one idiom common doesn't reach, since it doesn't contain 'sleep' as
        # its own segment.
        # 'delay_usec'/'delay_msec' are the same OS-singleton-wrapper idiom
        # as the 'env' additions below (`OS::get_singleton()->delay_usec(...)`)
        # — verified real, unambiguous call sites (core_bind.cpp:OS::delay_usec/
        # delay_msec).
        ('sleep', ['sleep_for', 'delay_usec', 'delay_msec']),
        # Same recall-oracle loop: bare 'getenv'/'putenv' (_TAXONOMY_COMMON)
        # never matches the cross-platform-engine OS-singleton wrapper idiom
        # (`OS::get_singleton()->get_environment(...)`) — verified real,
        # unambiguous call sites (core_bind.cpp:OS::get_environment/
        # set_environment/has_environment/unset_environment).
        ('env', ['get_environment', 'set_environment', 'has_environment', 'unset_environment']),
        # 'print_line'/'print_error'/'print_verbose' and the WARN_PRINT/
        # ERR_PRINT macros (case-insensitive segment match) are the
        # dominant logging idiom in engine code built this way — distinct
        # enough spellings that they don't collide with unrelated C++
        # (same shape as Go's klog/glog/logrus addition, BACK-629).
        ('log', [
            'spdlog::info', 'spdlog::warn', 'spdlog::error',
            'print_line', 'print_error', 'print_verbose',
            'warn_print', 'err_print',
        ]),
    ],
    # BACK-722 (sideeffects-recall-oracle, thirteenth language, first
    # BACK-718 slice after C): Kong API Gateway `kong/` (samples/lua/kong,
    # 605 files). Lua had NO entry at all before this loop -- every .lua
    # file fell all the way through to the fully-unscoped _COMPILED_ALL
    # table (see _COMPILED_COMMON_ONLY's comment, the loop's single biggest
    # finding: this silently classified ordinary `table.insert(t, x)` /
    # bare `select('#', ...)` as 'db' via Python/PHP's scoped bare verbs
    # leaking through). Kong's dominant idiom throughout its DAO/connector
    # layer is Lua's own colon method-call syntax (`conn:query(sql)`,
    # `self.connector:escape_literal(x)`, `httpc:request_uri(url)`) --
    # `classify_call`'s tokenizer (_DELIM_RE) didn't split on `:` at all
    # before this loop, so every colon call collapsed to ONE opaque glued
    # segment (`"self:query"`) that could never match ANY pattern regardless
    # of taxonomy content -- fixed at the tokenizer level (_DELIM_RE), the
    # single biggest recall driver this loop (61.62%->86%+ alone), same
    # shape as Rust's macro_invocation node-type gap.
    #
    # Bare 'insert'/'select'/'update'/'delete' (Python/PHP's own scoped db
    # verbs, BACK-636) were corpus-checked and DECLINED for Lua, not just
    # skipped: `table.insert`/`table.remove` (Lua stdlib, ~80/4 corpus call
    # sites) and bare `select(...)` (Lua's builtin vararg-count idiom) use
    # 'insert'/'select' for something completely unrelated to a database;
    # `digest:update(chunk)` (OpenSSL streaming hash update,
    # plugins/basic-auth/crypto.lua) and `dict:delete(...)`/`lru:delete(...)`/
    # `kong_shm:delete(...)` (ngx.shared.DICT / mlcache in-memory cache
    # eviction, not postgres/cassandra) corpus-confirm 'update'/'delete' the
    # same way -- the exact BACK-633/636 collision-prone-generic-verb class,
    # corroborated in a Lua-specific idiom pair.
    'lua': [
        ('db', [
            # Kong's own postgres/cassandra DAO+connector verbs -- checked
            # bare-colon-call receivers corpus-wide (self/connector/
            # connection/conn/r/lconn for query; self/connector for
            # escape_literal; DAO-shaped names for upsert), zero non-db hits
            # found (unlike insert/select/update/delete above). 'query' was
            # already an accepted cross-language _COMPILED_ALL exposure via
            # python/php's own pre-existing bare 'query' entry (BACK-636) --
            # this addition changes nothing about that exposure, only adds
            # lua-scoped matching. 'upsert' is a genuinely new token
            # (scripts/check_taxonomy_collisions.py: Java 32 / Zig 31 /
            # Kotlin 30 / Ruby 16 / TS 11 hits) but kept -- "upsert" carries
            # no OTHER common meaning in any of those languages (unlike
            # 'truncate' below), so even an unscoped hit is overwhelmingly
            # likely to be a real db upsert operation, not a collision.
            'query', 'escape_literal', 'upsert',
            # pgmoon (lua-postgres driver) / cassandra: bare module-name
            # words, corpus-checked (16 / 2 files respectively), no
            # collision risk -- distinctive enough not to appear as an
            # ordinary identifier anywhere else.
            'pgmoon', 'cassandra',
            # DECLINED: bare 'truncate', despite 10/10 clean DAO-shaped
            # corpus evidence in Lua itself (db/dao/init.lua's DAO:truncate,
            # connector:truncate). check_taxonomy_collisions.py found real,
            # ambiguous cross-language exposure via _COMPILED_ALL (unscoped
            # mode): Java 572, Go 217, Zig 98, Ruby 179, TS 94, Rust 39,
            # C++ 32 hits -- unlike 'upsert', 'truncate' has a completely
            # unrelated, common, non-db meaning in most of those languages
            # (POSIX ftruncate/Windows SetEndOfFile-shaped FILE truncation:
            # C's ftruncate, .NET Stream.SetLength-adjacent truncate
            # wrappers, Go's os.Truncate). Same declined-bare-verb shape as
            # the C loop's POSIX connect/accept/send/recv and every prior
            # loop's BACK-633/636 class -- one residual Lua 'db' miss left
            # open (db/strategies/postgres/connector.lua:truncate) rather
            # than risk a file-vs-db false positive elsewhere.
        ]),
        ('file', [
            # io.popen: COMMON's bare 'open(' pattern already catches
            # `io.open(...)` (tokenizes to a segment 'open', matching the
            # common pattern directly) but NOT `io.popen(...)` -- 'popen' is
            # a distinct segment, not a substring match (by design, see
            # module docstring). io.write/io.read: receiver-scoped to the
            # literal 'io' module (two-segment, not a bare 'write'/'read'
            # verb -- those stay unscoped everywhere per the conservative
            # philosophy, same reasoning as declining bare 'request' above).
            # os.remove: Lua/POSIX file deletion, unambiguous, corpus-
            # confirmed (cmd/start.lua's cleanup_dangling_unix_sockets).
            'io.popen', 'io.write', 'io.read', 'os.remove',
            # DECLINED: `pl_file.write(...)` (cmd/hybrid.lua:generate_cert,
            # Penlight's file module) -- `pl_file` is a local require()
            # alias, not a fixed stdlib name; same class as Python's
            # declined `async_get_clientsession` (project-specific idiom
            # tied to a variable name a taxonomy pattern can't reach
            # generically). One residual 'file' miss left open.
        ]),
        ('http', [
            # `local http = require("resty.http"); local httpc = http.new()`
            # -- OpenResty's cosocket-based HTTP client, the dominant (only)
            # outbound-HTTP idiom in this corpus; Kong has no raw POSIX
            # socket idiom the way Redis/C did (C loop's declined bare
            # connect/accept/send/recv class doesn't apply the same way
            # here -- OpenResty wraps it all behind resty.http/ngx.socket).
            'http.new', 'request_uri',
            # ngx.location.capture: nginx subrequest (init.lua's buffered-
            # proxy path) -- three-segment, unambiguous.
            'ngx.location.capture',
            # ngx.socket.{tcp,udp,connect,stream}: raw cosocket creation,
            # used by the unix-domain-socket plugin-server RPC transport
            # and a handful of DNS/stream modules. Two-segment prefix
            # (trailing-delimiter convention, same shape as COMMON's
            # 'redis->') matches all four verbs via one pattern.
            'ngx.socket.',
        ]),
        # NOTE: bare `httpc:request(`/`httpc:connect(`/`ngx.socket.connect`'s
        # own verb 'connect' was considered and DECLINED as its own separate
        # bare pattern -- same finding as the C loop's declined POSIX
        # connect/accept/send/recv (scripts/check_taxonomy_collisions.py:
        # 'connect' is a catastrophic cross-language collision, 3,557 C++
        # hits, 194 Go hits, from that loop's own measurement). 'request'
        # bare was also considered and declined: it would wrongly tag every
        # `kong.request.get_headers()`/`kong.request.get_method()`/etc PDK
        # accessor call (Kong's OWN incoming-request API, used constantly
        # in every plugin) as an outbound 'http' effect -- `kong.request.*`
        # contains the segment 'request' as a contiguous subsequence match.
        # request_uri (above) is unaffected -- distinctive enough that no
        # kong.request.* accessor is named exactly that.
    ],
    # BACK-718/BACK-725 (Zig, fourteenth side-effect-recall language). Corpus:
    # TigerBeetle (samples/zig/tigerbeetle/src, distributed financial db) --
    # a distinctive shape for a receiverless-verb-poor language: Zig has real
    # dot-receiver syntax (unlike C/Lua-without-`:`), but its dominant io
    # boundary is TigerBeetle's OWN thin storage/network wrapper object
    # (`io.read`/`io.write`/`io.connect`/etc, not a stdlib call), so the same
    # "scope a two-segment `io.<verb>` pattern instead of a bare verb"
    # technique the Lua loop used for `io.write`/`io.read` (file) applies
    # again here, plus its network counterpart (`io.connect`/`io.accept`/
    # `io.listen`/`io.recv`/`io.send`) -- corpus-confirmed the dominant,
    # in fact ONLY, network-boundary idiom in this corpus (message_bus.zig,
    # cdc/amqp.zig, testing/vortex/faulty_network.zig). Two-/three-segment
    # scoped patterns carry the same "can't cross-language-collide" safety
    # property check_taxonomy_collisions.py's own docstring describes for
    # `_TAXONOMY_BY_LANG` entries -- checked anyway (see the module's own
    # zig-scoped bare additions below for the ones that DO need the corpus
    # check, since they're single-segment).
    'zig': [
        ('file', [
            # TigerBeetle's storage abstraction (storage.zig/io.zig):
            # `grid.superblock.storage.read_sectors(...)`/
            # `client_replies.storage.write_sectors(...)` -- corpus-wide the
            # ONLY two call sites for on-disk sector I/O in the whole
            # codebase (io/linux.zig's own io_uring `prep_read`/`prep_write`
            # submission-queue setup is a single internal call site each,
            # not a corpus-wide idiom worth a pattern). Distinctive compound
            # names, no cross-language collision risk (checked below).
            'read_sectors', 'write_sectors',
            # Two-segment `io.<verb>`, scoped narrower than a bare
            # 'read'/'write' verb (which would be a catastrophic collision,
            # same class as the C/Lua loops' declined bare send/recv) --
            # same technique as Lua's `io.write`/`io.read` file-bucket
            # entry (this table's 'lua' key above), unrelated module
            # despite the identical receiver name (Lua's `io` is the
            # stdlib file module; TigerBeetle's `io` is its own IO/event
            # loop object) -- coincidence, not a shared mechanism.
            'io.write', 'io.read', 'io.fsync', 'io.open_data_file',
            # Zig stdlib file/dir idioms -- camelCase compounds, tokenizer
            # doesn't split camelCase so each is its own distinct segment
            # (same shape as C#'s SaveChangesAsync miss): `std.fs.cwd().
            # openDir(...)`/`project_root.openDir(...)` (stdx/shell.zig,
            # the dominant file-tree-walk idiom), `std.fs.cwd().
            # openFile(...)`, `std.fs.cwd().makeOpenPath(...)`/`.deleteTree
            # (...)` (build_multiversion.zig temp-dir lifecycle),
            # `std.fs.selfExePath(...)`/`std.fs.cwd().statFile(...)`
            # (multiversion.zig's self-executable-path resolution).
            'opendir', 'openfile', 'makeopenpath', 'deletetree',
            'selfexepath', 'statfile',
            # Second measurement pass (post first taxonomy cut, 81.48% file
            # recall): `std.fs.copyFileAbsolute(...)` (testing/vortex/
            # supervisor.zig replica_install), `std.fs.cwd().
            # realpathAlloc(...)` (multiversion.zig print_information) --
            # both distinctive camelCase compounds, same shape as the first
            # batch. `posix.pwrite(...)`/`posix.fsync(...)` (io/linux.zig's
            # own io_uring completion-path fallback and directory-fsync-
            # after-write durability call) -- bare POSIX syscall names,
            # corpus-collision-checked below (universally file-I/O-only
            # across every language's corpus, unlike e.g. 'read'/'write'
            # alone -- 'fsync'/'pwrite' carry no other common meaning).
            'copyfileabsolute', 'realpathalloc', 'pwrite', 'fsync',
            # DECLINED: `std.fs.File{ .handle = fd }` (io/common.zig
            # aof_blocking_close) -- a STRUCT LITERAL construction, not a
            # call node at all; classify_call only ever sees callee text
            # from an actual call expression, so there is no mechanism to
            # attribute this without a new struct-literal-effects channel
            # (same class of structural gap as TypeScript's BACK-644
            # property-read miss, out of scope for a taxonomy-only fix).
            # One residual 'file' miss left open for this reason.
        ]),
        ('http', [
            # TigerBeetle has no HTTP client; the network-boundary
            # equivalent is its own IO object's connection-lifecycle verbs
            # (message_bus.zig's `bus.io.connect/.accept/.listen/.recv/
            # .send/.send_now`, cdc/amqp.zig's own `connect`/`send`/
            # `receive` AMQP-transport methods, testing/vortex/
            # faulty_network.zig's fault-injection proxy). Two-segment
            # `io.<verb>` scoping is the load-bearing safety property here:
            # bare 'connect'/'accept'/'listen'/'send'/'recv' were the C
            # loop's declined POSIX-socket class (catastrophic collision,
            # 3,947 Java `accept` hits alone) and Lua's declined
            # `httpc:connect`/bare `request` class -- scoping to the
            # two-segment 'io.<verb>' shape avoids that exposure entirely
            # (a bare 'io' RECEIVER is comparatively rare and, per
            # `_RECEIVER_TAXONOMY`'s existing conservative design, still
            # only ever a receiver-fallback signal, not a verb match).
            'io.connect', 'io.accept', 'io.listen', 'io.recv',
            'io.send', 'io.send_now',
            # cdc/amqp.zig's own AMQP wire-protocol methods reuse the same
            # 'connect'/'send'/'receive' verbs but on a DIFFERENT receiver
            # shape (`self.connect(...)`/`amqp.send(...)`) -- not narrowed
            # to 'io.' there, so NOT separately added as a bare pattern
            # (would reintroduce the declined-bare-verb exposure); the
            # cdc/amqp.zig hits in this loop's sample all happen to ALSO
            # route through `self.io.*` internally one level down in the
            # same function body, so `io.<verb>` still catches them at
            # function-body granularity without a bare-verb addition.
            #
            # Second measurement pass: some corpus call sites go straight to
            # POSIX/`std.net` without going through the `io` wrapper at all
            # (`trace/statsd.zig:init_udp`'s `std.posix.connect(...)`,
            # `stdx/unshare.zig:linux_ip_link_loopback`'s
            # `std.posix.socket(...)`, `scripts/devhub.zig:devhub_metrics`'s
            # `std.net.tcpConnectToAddress(...)`). Two-segment
            # 'posix.<verb>' (matches both the fully-qualified `std.posix.X`
            # form and the common local-alias `const posix = std.posix;`
            # form via subsequence matching) is scoped exactly like `io.
            # <verb>` above -- NOT the declined bare 'connect'/'socket'
            # alone. `std.net.` (trailing-delimiter prefix convention,
            # same shape as Lua's `ngx.socket.` entry) catches any
            # `std.net.*` call regardless of the specific verb.
            'posix.connect', 'posix.accept', 'posix.socket', 'std.net.',
        ]),
        ('env', [
            # `std.process.getEnvVarOwned(...)` -- Zig's actual
            # env-var-read API (distinct from the older/simpler
            # `std.posix.getenv`, already covered by COMMON's bare
            # 'getenv'). CamelCase compound, tokenizer doesn't split it,
            # distinct token from COMMON's 'getenv'. `std.process.
            # getEnvMap(...)` -- the whole-environment-map variant
            # (stdx/shell.zig's Shell.create).
            'getenvvarowned', 'getenvmap',
        ]),
        ('log', [
            # `std.debug.print(...)` -- Zig's raw stdout/stderr debug-print
            # primitive, used corpus-wide for benchmark/test-harness output
            # where `std.log` would be too heavyweight (`stdx/testing/
            # bench.zig:report`, `lsm/binary_search.zig:random_search`
            # (gated by a LOCAL bool parameter confusingly also named
            # `log`, unrelated to std.log), `stdx/shell.zig:close`'s timing
            # report). Two-segment `debug.print` -- NOT bare 'print' (that
            # would be the same catastrophic collision class as Python's
            # print()/JS's console.log, declined everywhere this program
            # has touched a receiverless print idiom). 'debug' as a
            # receiver-like segment paired specifically with 'print' is a
            # safe, narrow pair no other corpus language's own hits
            # (checked: zero cross-language `debug.print(` hits in any
            # `samples/<lang>` tree).
            'debug.print',
        ]),
    ],
    # BACK-718/BACK-720 (sideeffects-recall-oracle, fifteenth language, after
    # C/Lua/Zig closed BACK-718's first three slices): GitBucket
    # (samples/scala, a real production Scala/Scalatra Git-hosting web app --
    # see scala/SCALA.md for the full corpus/methodology writeup). Two
    # candidate bare verbs considered and DECLINED here, kept only as a
    # documented finding (see SCALA.md): GitBucket's own Slick blocking-API
    # persistence layer (`Priorities.filter(...).firstOption`,
    # `query.insert(...)`, `query.update(...)`, `query.delete()`) is
    # syntactically INDISTINGUISHABLE from Scala's own built-in
    # collection/Option methods (`List.filter`, `Option.filter`) -- the
    # exact same already-declined bare-verb collision class as Lua's
    # insert/select/update/delete (BACK-636/BACK-633), just with NO
    # distinguishing receiver-name/dotted-prefix at all (unlike Python's
    # `session.query`, PHP's `$wpdb->query`, or Lua's `connector:query`).
    # `check_taxonomy_collisions.py` confirmed catastrophic cross-language
    # exposure for a scala-scoped `filter`/`insert`/`update`/`delete` (every
    # other corpus language's own collection/map methods use the identical
    # names) -- declined, `db` recall stays structurally low for this corpus.
    'scala': [
        ('db', [
            # Slick's blocking-API TERMINAL methods -- distinctive camelCase
            # compounds (tokenizer doesn't split camelCase, same shape as
            # C#'s SaveChangesAsync/Zig's openFile), NOT the bare
            # `filter`/`insert`/`update`/`delete`/`list`/`first`/`result`
            # verbs Slick chains them onto (see this table's own header
            # comment for why those are declined). `firstOption` alone is
            # GitBucket's single most common Slick terminal call (31 corpus
            # sites, e.g. `Priorities.filter(...).firstOption`) and, unlike
            # bare `first`, has no non-Slick meaning in any corpus language.
            'firstoption', 'withsession',
            # Slick 2.x-style DB handle acquisition -- dotted, GitBucket's
            # own `Database.forDataSource`/`Database.forURL` bootstrap
            # calls (servlet/InitializeListener.scala). Zero collision risk
            # (fully-qualified, Slick-specific).
            'database.fordatasource', 'database.forurl',
        ]),
        ('file', [
            # `new File(...)`/`new FileOutputStream(...)`/
            # `new FileInputStream(...)`/`new FileWriter(...)` -- java.io
            # interop, GitBucket's dominant non-JGit file-I/O idiom (100+
            # corpus call sites). Only visible at all after this loop's
            # `instance_expression` CALL_NODE_TYPES fix (see treesitter.py) --
            # the "new <Name>" callee-text convention already established for
            # PHP/C#'s `object_creation_expression` (e.g. PHP's 'new pdo').
            'new file', 'new fileoutputstream', 'new fileinputstream',
            'new filewriter',
            # Apache Commons `FileUtils.*` -- a single bare, distinctive
            # compound-noun receiver (dotted-prefix-equivalent via sliding-
            # window subsequence matching: `FileUtils.deleteDirectory`
            # tokenizes to ['fileutils','deletedirectory'], and the single
            # pattern token 'fileutils' matches regardless of trailing verb)
            # -- same "namespaced receiver, no bare verb" safety shape as
            # Zig's `std.net.`/Lua's `ngx.socket.` prefix entries. 18
            # deleteDirectory + 4 moveDirectory + 3 writeByteArrayToFile + 3
            # copyFile + 2 write + 2 readFileToString + 2 forceDelete + 1
            # each of readFileToByteArray/forceMkdirParent/forceMkdir/
            # deleteQuietly/copyDirectory corpus call sites, zero
            # non-file-I/O meaning.
            'fileutils',
            # java.io.File instance methods -- `.mkdirs()`/`.createNewFile()`
            # are compound (not bare 'mkdir'/'create') so carry negligible
            # collision risk versus the bare single-verb forms COMMON
            # already declines; corpus-checked, no non-file-I/O hits in any
            # other language's corpus.
            'mkdirs', 'createnewfile',
        ]),
        ('http', [
            # Apache HttpClient webhook-delivery idiom (WebHookService.scala
            # callWebHook): `new HttpPost(url)`/`new HttpGet(url)` --
            # constructor calls, only visible after the instance_expression
            # fix above. `httpClient.execute(httpPost)` itself was ALREADY
            # classified pre-fix via the pre-existing language-UNSCOPED
            # `_RECEIVER_TAXONOMY` 'httpclient' receiver entry (shared with
            # Python's httpx/aiohttp) -- no new pattern needed for that call.
            'new httppost', 'new httpget',
            # `HttpClientBuilder.create(...)...build()` (HttpClientUtil.scala
            # withHttpClient) -- client CONSTRUCTION/configuration, not the
            # request itself; added anyway since it's a distinctive compound
            # receiver name with zero collision risk and genuinely marks a
            # function that participates in this corpus's one real outbound-
            # HTTP code path.
            'httpclientbuilder',
        ]),
        ('env', [
            # `System.getProperty`/`System.getenv` — Scala interops directly
            # with java.lang.System, and language-scoping means Java's OWN
            # existing `_TAXONOMY_BY_LANG['java']` entry for this exact verb
            # (added BACK-639) does NOT extend to Scala files even though
            # both compile to the same JVM class — classify_call() only
            # merges COMMON + the file's OWN language bucket. Duplicated
            # here rather than shared, mirroring the java entry exactly
            # (`system.getenv` is redundant with COMMON's bare 'getenv' via
            # subsequence match, kept for symmetry/documentation).
            'system.getenv', 'system.getproperty',
        ]),
    ],
}

# Analyzer `language` values that share one _TAXONOMY_BY_LANG bucket.
_LANG_GROUP: Dict[str, str] = {
    'javascript': 'js', 'typescript': 'js', 'tsx': 'js', 'jsx': 'js',
}

# classify_call()'s kind-priority order (first match wins) — preserved from
# the original flat _TAXONOMY so merging common + per-language tables can't
# silently reorder which kind a dual-matching callee resolves to.
_KIND_ORDER = ['hard_stop', 'db', 'http', 'cache', 'session', 'file', 'env', 'log', 'sleep']


def _merge_by_kind(*taxonomies: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[str]]]:
    """Merge (kind, patterns) tables, concatenating patterns per kind and
    ordering kinds by _KIND_ORDER regardless of input order."""
    merged: Dict[str, List[str]] = {}
    for taxonomy in taxonomies:
        for kind, patterns in taxonomy:
            merged.setdefault(kind, []).extend(patterns)
    return [(kind, merged[kind]) for kind in _KIND_ORDER if kind in merged]


_DELIM_RE = re.compile(r'->|::|\.|:|\s+')


def _tokenize(s: str) -> List[str]:
    """Lowercase, strip PHP `$` sigil and trailing `(`, split on delimiters."""
    s = s.lower().strip()
    if s.endswith('('):
        s = s[:-1].rstrip()
    s = s.lstrip('$')
    parts = _DELIM_RE.split(s)
    return [p for p in parts if p]


def _compile(taxonomy: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[List[str]]]]:
    return [(kind, [_tokenize(p) for p in patterns]) for kind, patterns in taxonomy]


# Pre-compiled once at module load: the "no language given" table (identical
# match set to the pre-BACK-431-Issue-D flat _TAXONOMY) and one table per
# known language (common + that language's patterns only).
_COMPILED_ALL: List[Tuple[str, List[List[str]]]] = _compile(
    _merge_by_kind(_TAXONOMY_COMMON, *_TAXONOMY_BY_LANG.values())
)
_COMPILED_BY_LANG: Dict[str, List[Tuple[str, List[List[str]]]]] = {
    lang: _compile(_merge_by_kind(_TAXONOMY_COMMON, patterns))
    for lang, patterns in _TAXONOMY_BY_LANG.items()
}
# BACK-722 (Lua sideeffects-recall-oracle pre-flight): classify_call()'s
# `_COMPILED_BY_LANG.get(lang, _COMPILED_ALL)` fallback conflated two
# different situations that should not share a default. When `language` is
# genuinely omitted (None), unscoped-everywhere IS the documented, correct
# behavior. But when a REAL, known language name is passed and that language
# simply has no _TAXONOMY_BY_LANG entry YET (every language below the
# original eleven — at time of writing: lua, scala, dart, gdscript, zig, sql,
# elixir, hcl, graphql, dockerfile, powershell, bash, ...), `.get()` silently
# fell through to the SAME fully-unscoped _COMPILED_ALL table as the
# language=None case — the exact opposite of every entry's whole purpose
# (BACK-431 Issue D: "a Go file can no longer be tagged 'session' by a PHP
# builtin"). Confirmed live and corpus-verified on real Kong Lua source
# (samples/lua/kong) before this fix: `table.insert(t, x)` — ordinary Lua
# stdlib array-append, ubiquitous, ~80 corpus call sites — classified as
# 'db' (matching Python/PHP's scoped bare 'insert' verb through the unscoped
# fallback), and `select('#', ...)` — Lua's builtin vararg-count idiom —
# likewise classified as 'db' (Python/PHP's bare 'select' verb). Every
# not-yet-measured language was silently exposed to every OTHER language's
# collision-prone bare verbs with zero scoping protection. Fixed: an unknown-
# but-named language now falls back to COMMON-only (this language's real,
# intended scope until it gets its own _TAXONOMY_BY_LANG entry), not ALL.
_COMPILED_COMMON_ONLY: List[Tuple[str, List[List[str]]]] = _compile(_TAXONOMY_COMMON)


# BACK-285a: receiver-shape heuristics. After full-pattern matching fails,
# fall back to matching on a non-final segment of the callee. Catches calls
# like `cursor.execute`, `_log.warning`, `redis.get` where the verb varies
# but the receiver name is canonical. Non-final-only — `dict.get` (where
# `dict` is final-prefix and `get` is the trailing verb) does not match,
# and bare `cursor` (single segment) does not match. Project-specific
# receivers (tsx, evlog, services.trade_db, ...) belong in BACK-238's
# `.reveal.yaml` extension, not here.
# BACK-594: `conn`/`connection`/`session` (db) and bare `cache` (cache) were
# REMOVED — this fallback is language-unscoped and these are extremely common
# non-db/non-cache variable/package names, so they produced corpus-confirmed
# cross-language false positives: Go `conn.Close()`/`conn.Subprotocol()` -> db,
# Go `cache.NewListWatchFromClient(...)` -> cache (the k8s package literally
# named `cache`), Python aiohttp `session.get(url)` -> db, websocket
# `connection.send_result(...)` -> db. Real SQLAlchemy db calls that used to
# rely on the `session`/`connection` receiver are now caught precisely by the
# explicit `session.<orm-verb>` patterns in _TAXONOMY_BY_LANG['python'] and by
# the common `->execute`/`->query` verbs (`connection.execute`, `cursor.execute`).
# `cursor` (db) and `redis`/`memcache` (cache) are kept: they are specific
# enough to not collide with ordinary variable names.
_RECEIVER_TAXONOMY: List[Tuple[str, List[str]]] = [
    ('db', ['cursor', 'db', 'engine']),
    ('cache', ['redis', 'memcache']),
    ('log', ['logger', '_log', 'log', '_logger', 'ilogger', 'slf4j']),
    # BACK-640 (sideeffects-recall-oracle/java): 'requests' (Python's requests
    # library alias) removed — as a bare English plural noun it collided with
    # Java's `request.requests.get(i)` field access (a TermVectorsRequest
    # list, not HTTP), same class as BACK-594's conn/session/cache drop.
    # Redundant with explicit python http patterns (requests.get/post/put/
    # delete already in _TAXONOMY_BY_LANG['python']), so no recall loss.
    ('http', ['httpx', 'aiohttp', 'httpclient', '_httpclient']),
    # BACK-401: .NET BCL / JVM stdlib receivers for File/Directory/Path-style
    # I/O and env access — safe as non-final-only receiver matches (see
    # module docstring caution on why these aren't bare _TAXONOMY patterns).
    # 'path' (singular) removed BACK-416: it's an extremely common local-var
    # name and a Path object's methods (`path.resolveIndex()`, `path.getParent()`,
    # C# `Path.Combine`) are string/path manipulation, not I/O — real filesystem
    # work goes through the File/Directory/Files/Paths static classes (kept).
    # 'fs' added BACK-416: Node's filesystem module (`fs.writeFileSync`,
    # `fs.readFileSync`, `fs.promises.writeFile`) and Rust's aliased `fs::read`
    # — both were previously unclassified despite being clear file I/O.
    ('file', ['file', 'directory', 'files', 'paths', 'fs']),
    ('env', ['environment']),
]


# BACK-637: per-kind verb allowlist applied on top of _RECEIVER_TAXONOMY's
# receiver-name match. A receiver name alone is ambiguous when it's also a
# common local-variable name — `files.iterator()`/`.size()`/`.forEach()` is a
# `Stream<Path> files`/`List<Path> files` local var (Collection/Stream ops),
# not the JVM `Files` static class, but `_classify_by_receiver` couldn't tell
# them apart since matching is case-insensitive and receiver-only. Corpus-wide
# (samples/java, 44K files): `Files.<verb>` (the real static-class idiom,
# 3,120 call sites) and lowercase `files.<verb>` (the FP local-var idiom, 212
# call sites) have COMPLETELY disjoint verb sets — Files.* verbs below are
# I/O-shaped, the FP verbs are Collection/Stream-shaped (get/stream/size/
# contains/add/put/isEmpty/filter/addAll/iterator/toArray/map/clear/forEach/
# toList/putAll/merge). 'size' is deliberately EXCLUDED even though
# `Files.size(path)` is real NIO API: it was the #3 FP verb in the corpus
# (21 local-var `.size()` calls) and per the conservative-classification
# philosophy (see BACK-644 property-channel comment), a miss is cheaper than
# a false positive. Only the 'file' kind has a filter — db/cache/log/http/env
# receiver matches are unaffected (no filter entry = no behavior change).
# Verbs also include the Node `fs.*`/`.NET Directory/Path` static-method
# idioms already relied upon by other languages' 'file' receiver matches, so
# this filter can't regress them.
_RECEIVER_VERB_FILTER: Dict[str, frozenset] = {
    'file': frozenset({
        # JVM NIO `Files`/`Directory` static class (corpus histogram)
        'exists', 'notexists', 'createdirectories', 'createdirectory',
        'writestring', 'copy', 'write', 'deleteifexists', 'delete',
        'createfile', 'newinputstream', 'newoutputstream', 'readalllines',
        'isdirectory', 'move', 'newdirectorystream', 'list', 'readallbytes',
        'readstring', 'newbufferedwriter', 'newbufferedreader',
        'isregularfile', 'isreadable', 'iswritable', 'isexecutable',
        'issamefile', 'issymboliclink', 'createsymboliclink', 'createlink',
        'readsymboliclink', 'walkfiletree', 'walk', 'lines', 'find',
        'mismatch', 'readattributes', 'setattribute', 'getattribute',
        'newbytechannel', 'getlastmodifiedtime', 'setlastmodifiedtime',
        'probecontenttype',
        # Node `fs`/.NET `Directory`/`Path` static-method idioms
        'writefilesync', 'readfilesync', 'existssync', 'mkdirsync',
        'unlinksync', 'renamesync', 'rmsync', 'appendfilesync',
        'copyfilesync', 'readdirsync', 'writefile', 'readfile', 'mkdir',
        'unlink', 'rename', 'rm', 'appendfile', 'copyfile', 'readdir',
        'getfiles', 'enumeratefiles', 'metadata', 'read', 'openread',
        'openwrite', 'create', 'appendalltext', 'appendalllines',
        'appendtext',
    }),
}


def _segments_contain(callee_segs: List[str], pattern_segs: List[str]) -> bool:
    """True if pattern_segs appears as a consecutive sub-sequence of callee_segs."""
    n = len(pattern_segs)
    if n == 0 or n > len(callee_segs):
        return False
    for i in range(len(callee_segs) - n + 1):
        if callee_segs[i:i + n] == pattern_segs:
            return True
    return False


def _classify_by_receiver(callee_segs: List[str]) -> Optional[str]:
    """Classify by matching a non-final segment against receiver names.

    BACK-637: if the matched kind has a verb allowlist in
    _RECEIVER_VERB_FILTER, the final segment (the verb) must also be in it —
    a receiver-name match alone isn't enough for kinds where the receiver
    name collides with common local-variable names (e.g. `files`).
    """
    if len(callee_segs) < 2:
        return None
    non_final = callee_segs[:-1]
    verb = callee_segs[-1]
    for kind, receivers in _RECEIVER_TAXONOMY:
        for receiver in receivers:
            if receiver in non_final:
                allowed_verbs = _RECEIVER_VERB_FILTER.get(kind)
                if allowed_verbs is not None and verb not in allowed_verbs:
                    continue
                return kind
    return None


# BACK-547 (sideeffects-recall-oracle/kotlin, tenth language): Java/Kotlin's
# `xxxDao`/`XxxDao` naming convention (Data Access Object — Android's Room,
# Spring's DAO layer, Tivi's SQLDelight-backed daos) is the dominant db-access
# receiver, but the generated/hand-written method names carry no consistent
# verb (`showDao.getShowWithIdOrThrow(...)`, `seasonsDao.seasonWithId(...)`,
# `episodeWatchEntryDao.entriesForShowIdWithSendPendingActions(...)`) — an
# open-ended vocabulary no fixed pattern list can enumerate. Corpus (Tivi
# data/, 252 files): 27 files, 100+ call sites, all unclassified before this
# fix. Suffix match (not exact-segment, unlike `_RECEIVER_TAXONOMY`) because
# the receiver is a whole identifier like `showdao`/`seasonsdao`, never the
# bare word `dao` alone. Checked for collisions across every language's
# sample corpus (samples/): zero non-db `*dao` identifiers used as a call
# receiver.
_RECEIVER_SUFFIX_TAXONOMY: List[Tuple[str, List[str]]] = [
    ('db', ['dao']),
]


def _classify_by_receiver_suffix(callee_segs: List[str]) -> Optional[str]:
    """Classify by a non-final segment ENDING WITH a known receiver suffix."""
    if len(callee_segs) < 2:
        return None
    non_final = callee_segs[:-1]
    for kind, suffixes in _RECEIVER_SUFFIX_TAXONOMY:
        for suffix in suffixes:
            if any(seg.endswith(suffix) for seg in non_final):
                return kind
    return None


def classify_call(callee: str, language: Optional[str] = None) -> Optional[str]:
    """Return the taxonomy kind for a callee string, or None if unclassified.

    *language* scopes matching to common + that language's patterns (e.g. a
    PHP-only builtin like `session_start` won't fire for a Go file). Omit it
    to match against common + every known language's patterns (unscoped).
    """
    if not callee:
        return None
    callee_segs = _tokenize(callee)
    if not callee_segs:
        return None
    lang = _LANG_GROUP.get(language, language) if language else None
    # BACK-722: a known-but-unmapped language (e.g. lua, scala, dart, zig —
    # any language with no _TAXONOMY_BY_LANG entry yet) scopes to COMMON
    # only, never the fully-unscoped ALL table (see _COMPILED_COMMON_ONLY's
    # comment). Only a genuinely omitted language (None) is unscoped.
    if lang:
        taxonomy = _COMPILED_BY_LANG.get(lang, _COMPILED_COMMON_ONLY)
    else:
        taxonomy = _COMPILED_ALL
    for kind, pattern_list in taxonomy:
        for pattern_segs in pattern_list:
            if _segments_contain(callee_segs, pattern_segs):
                return kind
    return _classify_by_receiver(callee_segs) or _classify_by_receiver_suffix(callee_segs)


# ---------------------------------------------------------------------------
# Property-access channel (BACK-644)
# ---------------------------------------------------------------------------
# classify_call() can only ever see callee text, because its sole input is
# range_calls() (nav_calls.py), which walks call nodes exclusively. An env read
# that is a bare property/subscript access — Node's `process.env.FOO`, Ruby's
# `ENV['FOO']`, Python's `os.environ['FOO']` — contains no call node anywhere,
# so it never becomes a callee string and no taxonomy entry can match it: an
# ('env', ['process.env']) entry was verified permanently dead (0/26 corpus
# hits) before being reverted. This second channel walks member-access and
# subscript nodes instead.
#
# It is deliberately far narrower than the call taxonomy. A call *name* is
# strong evidence of an effect; a property read is not (`config.env`, `a.b.c`
# are ordinary reads), so this matches an explicit allowlist of env bases only
# and never classifies by shape — per the conservative-classification law, a
# wrong classification is worse than an unclassified read.
#
# Corpus scale, all invisible before this: 760 `process.env` reads in VS Code,
# 534 `ENV[` reads in Discourse, 8 `os.environ[` reads in Home Assistant.
_PROPERTY_SUBSCRIPT_NODES: frozenset = frozenset({
    'subscript',             # Python: os.environ['FOO']
    'subscript_expression',  # JS/TS:  process.env['FOO']
    'element_reference',     # Ruby:   ENV['FOO']
})

_PROPERTY_NODES: frozenset = _MEMBER_ACCESS_NODES | _PROPERTY_SUBSCRIPT_NODES

# Env bases, matched CASE-SENSITIVELY against the base's exact source text —
# NOT tokenized through _tokenize() like the call taxonomy.
#
# Case is load-bearing: Ruby's `ENV['X']` is the process environment, but
# `env['X']` is Rack's request hash — an unrelated thing, and Discourse has 199
# of them against 534 real `ENV[` reads. _tokenize() lowercases, so the call
# taxonomy structurally cannot tell those apart; that is also why Ruby's
# `ENV.fetch(...)` call form is left unclassified rather than given an
# ('env', ['env.fetch']) entry that would equally match Rack's `env.fetch(...)`
# (8 occurrences in Discourse — a miss, but a miss is cheaper than 199 FPs).
#
# PHP ($_ENV) is deliberately absent: WordPress has 1 occurrence across 5,291
# files, so there is no corpus evidence to justify a pattern. PHP's real idiom
# is `getenv()`, already classified by the call channel.
_ENV_BASES_BY_LANG: Dict[str, Tuple[str, ...]] = {
    'js': ('process.env',),
    'python': ('os.environ',),
    'ruby': ('ENV',),
}


def _env_property_bases(language: Optional[str]) -> Tuple[str, ...]:
    """Env bases for *language*, or every known base when unscoped.

    Mirrors classify_call()'s unscoped fallback (_COMPILED_ALL): omitting the
    language checks every language's bases.
    """
    if language:
        lang = _LANG_GROUP.get(language, language)
        return _ENV_BASES_BY_LANG.get(lang, ())
    return tuple(base for bases in _ENV_BASES_BY_LANG.values() for base in bases)


def _collect_property_effects(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return env property/subscript accesses in a line range (BACK-644).

    Reads dominate, but an env assignment *target* (`os.environ['X'] = '1'`) is
    an env effect too and is reported here — note --statewrites merges only the
    call channel, since its own assignment walk already owns that write.
    """
    bases = _env_property_bases(language)
    if not bases:
        return []
    from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415

    results: List[Dict[str, Any]] = []
    callee_spans = set()
    stack = [func_node]
    while stack:
        node = stack.pop()
        line = node.start_position().row + 1
        if node.end_position().row + 1 < from_line or line > to_line:
            continue
        kind = _zero_arg(node, 'kind')
        if kind in CALL_NODE_TYPES:
            # A call's own callee belongs to the call channel: `os.environ.get`
            # is an `attribute` whose base text is exactly `os.environ`, so
            # without this it would be reported a second time here, on the very
            # line classify_call() already tagged 'env'. Only the callee node
            # itself is suppressed, never its subtree — in
            # `process.env.FOO.trim()` the receiver `process.env.FOO` is a real
            # env read that must still be found.
            #
            # 'function' is the callee field wherever the callee is a single
            # node (Python `call`, JS `call_expression`). Ruby's `call` instead
            # exposes 'receiver'/'method' separately, with no node spanning
            # `receiver.method` at all (see _extract_callee) — there child(0) is
            # the RECEIVER, so the generic fallback would suppress the very
            # reads we want: `ENV["X"]` in `ENV["X"].blank?`. That cost 80 real
            # Discourse reads (85.5% -> 99.6% recall) in BACK-644 corpus
            # validation. A receiver-less Ruby call (`puts(x)`) has no receiver
            # field and correctly falls through to child(0).
            callee = node.child_by_field_name('function')
            if callee is None and node.child_by_field_name('receiver') is None:
                callee = node.child(0)
            if callee is not None:
                callee_spans.add((_zero_arg(callee, 'start_byte'), _zero_arg(callee, 'end_byte')))
        elif kind in _PROPERTY_NODES and (_zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte')) not in callee_spans:
            # child(0) is the base in every shape this matches: the receiver of
            # a member access (`process.env` in `process.env.FOO`) and the
            # subject of a subscript (`os.environ` in `os.environ['FOO']`).
            # Requiring the base to be the *whole* match keeps a bare
            # `process.env` (no key read) unclassified — passing env around is
            # not itself an env read.
            base = node.child(0)
            if base is not None and from_line <= line <= to_line and get_text(base) in bases:
                results.append({
                    'line': line, 'callee': get_text(node), 'first_arg': None,
                    'has_more_args': False, 'kind': 'env', 'via': 'property',
                })
        stack.extend(reversed(_children(node)))
    return results


def collect_effects(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return classified side-effect sites in a line range, in line order.

    Two independent channels feed this (BACK-644):
        call     -- range_calls() call sites, classified by classify_call()
        property -- bare env property/subscript reads, which contain no call
                    node and so can never be classified from callee text

    Each item is a dict:
        line      -- 1-indexed line of the site
        callee    -- callee name, or full expression text for a property read
        first_arg -- first argument text (always None for a property read)
        kind      -- taxonomy label, or None if unclassified
        via       -- 'call' or 'property'
    """
    results = []
    for call in range_calls(func_node, from_line, to_line, get_text):
        kind = classify_call(call.get('callee') or '', language)
        results.append({**call, 'kind': kind, 'via': 'call'})
    results.extend(
        _collect_property_effects(func_node, from_line, to_line, get_text, language)
    )
    results.sort(key=lambda r: r['line'])
    return results


def format_effect_target(effect: Dict[str, Any]) -> str:
    """Render an effect's target the way it appears in source.

    A call renders with its first argument (`os.getenv(HOME)`); a property read
    (BACK-644) is not a call and must not get the `()` suffix that would imply
    one — it renders bare (`process.env.FOO`).
    """
    target = effect['callee'] or '(unknown)'
    if effect.get('via') == 'property':
        return target
    first_arg = effect.get('first_arg')
    if not first_arg:
        return f'{target}()'
    return f'{target}({first_arg}{"..." if effect.get("has_more_args") else ""})'


def _resolve_definition_node(file_path: str, name: str, analyzer_cache: Dict[str, Any]):
    """Best-effort: find *name*'s function node in *file_path*, caching the analyzer.

    Returns (node, start_line, end_line, get_text, language) or None if the
    file isn't tree-sitter analysable or the name can't be located — callers
    should skip that hop rather than treat it as fatal (this walk is a
    best-effort blast-radius read, not a correctness-critical resolution).
    """
    from ...file_handler import _find_element_node  # noqa: I006 — deferred, avoids cli/adapters cycle
    from ...registry import get_analyzer  # noqa: I006
    from ...treesitter import TreeSitterAnalyzer  # noqa: I006

    analyzer = analyzer_cache.get(file_path)
    if analyzer is None:
        analyzer_class = get_analyzer(file_path, allow_fallback=True)
        if analyzer_class is None:
            analyzer_cache[file_path] = False
        else:
            try:
                analyzer = analyzer_class(file_path)
            except Exception:
                analyzer = False
            analyzer_cache[file_path] = analyzer
    if not analyzer or not isinstance(analyzer, TreeSitterAnalyzer) or not analyzer.tree:
        return None

    node = _find_element_node(analyzer, name)
    if node is None:
        return None
    start = node.start_position().row + 1
    end_node = getattr(analyzer, '_function_end_node', lambda n: n)(node)
    end = end_node.end_position().row + 1
    return end_node, start, end, analyzer._get_node_text, getattr(analyzer, 'language', None)


def collect_effects_transitive(
    path: str,
    root_name: str,
    root_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
    depth: int = 2,
) -> List[Dict[str, Any]]:
    """Follow calls into project-local helpers, classifying effects across hops.

    Hop 0 is the entry function's own body (identical to collect_effects). Each
    subsequent hop resolves calls that land on a project-local definition —
    reusing the same bare-name + language-family scoping the calls:// recursive
    walk (find_callees_recursive) already relies on — and classifies that
    definition's own body too. An unresolved or cross-language call terminates
    that branch: it's already covered by collect_effects's direct name-pattern
    match at the hop that made it (BACK-545 design doc), so nothing is lost by
    not chasing it further.

    Each returned effect carries 'hop' (0-indexed) and 'chain' (the call path
    that reached it, e.g. ['handle_request', '_save', 'db_execute']).
    """
    from .analysis import collect_structures  # noqa: I006
    from ..calls.index import _build_forward_index, _bare_callee_name, _lang_family  # noqa: I006

    depth = max(1, min(depth, 5))

    hop0 = collect_effects(root_node, from_line, to_line, get_text, language)
    for e in hop0:
        e['hop'] = 0
        e['chain'] = [root_name]
    results: List[Dict[str, Any]] = list(hop0)

    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    structures = collect_structures(str(directory))
    forward = _build_forward_index(structures, include_builtins=False)

    root_family = _lang_family(path) if path else ''
    visited = {root_name}
    frontier = [(root_name, root_family, [root_name])]
    analyzer_cache: Dict[str, Any] = {}

    for hop in range(1, depth + 1):
        next_frontier: List[Tuple[str, str, List[str]]] = []
        for name, family, chain in frontier:
            defs = forward.get(name, [])
            if family:
                defs = [d for d in defs if _lang_family(d['file']) == family]
            for defn in defs:
                for callee in defn['calls']:
                    tail = _bare_callee_name(callee)
                    if tail in visited:
                        continue
                    candidates = forward.get(tail, [])
                    if family:
                        candidates = [c for c in candidates if _lang_family(c['file']) == family]
                    if not candidates:
                        continue
                    visited.add(tail)
                    callee_file = candidates[0]['file']
                    resolved = _resolve_definition_node(callee_file, tail, analyzer_cache)
                    if resolved is None:
                        continue
                    node, start, end, callee_get_text, callee_language = resolved
                    new_chain = chain + [tail]
                    hop_effects = collect_effects(node, start, end, callee_get_text, callee_language)
                    for e in hop_effects:
                        e['hop'] = hop
                        e['chain'] = new_chain
                        e['file'] = callee_file
                    results.extend(hop_effects)
                    next_frontier.append((tail, family or _lang_family(callee_file), new_chain))
        if not next_frontier:
            break
        frontier = next_frontier

    return results


def render_effects(
    effects: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
    include_unclassified: bool = False,
) -> str:
    """Render collect_effects output as text (flat, in line order)."""
    visible = [e for e in effects if e['kind'] is not None or include_unclassified]
    if not visible:
        return f'No classified side effects found in lines {from_line}–{to_line}'

    kind_width = max(len(e['kind'] or '?') for e in visible)
    lines = []
    for e in visible:
        kind = e['kind'] or '?'
        lines.append(f'L{e["line"]:<6}  {kind:<{kind_width}}  {format_effect_target(e)}')
    return '\n'.join(lines)


def render_effects_transitive(
    effects: List[Dict[str, Any]],
    root_name: str,
    depth: int,
    include_unclassified: bool = False,
) -> str:
    """Render collect_effects_transitive output, grouped by hop/call chain."""
    visible = [e for e in effects if e['kind'] is not None or include_unclassified]
    if not visible:
        return (
            f'No classified side effects found in {root_name} '
            f'or its callees (--transitive, depth={depth})'
        )

    kind_width = max(len(e['kind'] or '?') for e in visible)
    groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = OrderedDict()
    for e in visible:
        key = tuple(e.get('chain') or [root_name])
        groups.setdefault(key, []).append(e)

    blocks = []
    for chain, group_effects in groups.items():
        hop = group_effects[0].get('hop', 0)
        if hop == 0:
            header = f'[hop 0] {root_name} (own body)'
        else:
            header = f"[hop {hop}] via {' → '.join(chain)}"
        lines = [header]
        for e in group_effects:
            kind = e['kind'] or '?'
            lines.append(f'  L{e["line"]:<6}  {kind:<{kind_width}}  {format_effect_target(e)}')
        blocks.append('\n'.join(lines))
    return '\n'.join(blocks)
