"""Nav feature tests: classify_call / sideeffects taxonomy coverage.

Split from test_ast_nav_probe_features.py (BACK-1151) -- covers
classify_call/collect_effects/render_effects and the per-language
sideeffect-category widening regressions (db/file/http/log/sleep/env
taxonomy, --sideeffects surface).
"""

"""Tests for probe-inspired nav features added in BACK-156 through BACK-160.

Covers:
  collect_exits()    -- BACK-156/159 (--exits / --flowto)
  all_var_flow()     -- BACK-160 foundation
  collect_deps()     -- BACK-160 (--deps)
  collect_mutations()-- BACK-160 (--mutations)
  render_branchmap() -- BACK-158 (--ifmap / --catchmap)
  render_exits()     -- BACK-159
  render_deps()      -- BACK-160
  render_mutations() -- BACK-160

Also covers flat-file behaviour (Change A: root_node fallback) indirectly
through the nav functions accepting root_node as scope_node.
"""

import textwrap
import unittest

import tree_sitter_language_pack as ts

import pytest
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


# ---------------------------------------------------------------------------
# Parse helpers (shared with test_ast_nav.py pattern)
# ---------------------------------------------------------------------------

def _parse_php(code: str):
    """Parse PHP code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('php')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


class TestClassifyCall(unittest.TestCase):

    def test_db_mysql_query(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('mysql_query'), 'db')

    def test_db_execute_method(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->execute'), 'db')

    def test_http_curl_exec(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('curl_exec'), 'http')

    def test_http_requests_get(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('requests.get'), 'http')

    def test_cache_memcache_set(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('memcache_set'), 'cache')

    def test_log_error_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('error_log'), 'log')

    def test_file_fopen(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('fopen'), 'file')

    def test_file_put_contents(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file_put_contents'), 'file')

    def test_python_os_fdopen(self):
        # BACK-851: os.fdopen is the write leg of the atomic-write idiom
        # (`with os.fdopen(fd, 'wb') as fh: ...`) — was unclassified even
        # though os.rename/os.unlink/os.mkdir already cover the same shape.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.fdopen', 'python'), 'file')

    def test_python_os_replace(self):
        # BACK-851: os.replace is the atomic-rename-into-place leg of the
        # same idiom, unclassified for the same reason.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.replace', 'python'), 'file')

    def test_sleep(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('sleep'), 'sleep')

    def test_usleep(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('usleep'), 'sleep')

    def test_log_swift_nslog(self):
        # BACK-498 quick win: NSLog is Swift/Cocoa's unambiguous logging call.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('NSLog', 'swift'), 'log')

    def test_log_swift_os_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os_log', 'swift'), 'log')

    def test_swift_print_stays_unclassified(self):
        # print is a plain stdout write, not a log call — matches tier1
        # Java/C#/Python treatment (bare print/println/System.out unclassified).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('print', 'swift'))

    def test_csharp_db_executereader(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('ExecuteReader', 'csharp'), 'db')

    def test_csharp_http_getasync(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('client.GetAsync', 'csharp'), 'http')

    def test_csharp_file_writealltext(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.WriteAllText', 'csharp'), 'file')

    def test_csharp_env_getenvironmentvariable(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Environment.GetEnvironmentVariable', 'csharp'), 'env')

    def test_csharp_log_loginformation(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_logger.LogInformation', 'csharp'), 'log')

    def test_csharp_sleep_task_delay(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Task.Delay', 'csharp'), 'sleep')

    def test_csharp_scoped_to_csharp(self):
        # These are csharp-only patterns — must not leak into other languages.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('ExecuteReader', 'python'))

    def test_ruby_file_write(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.write', 'ruby'), 'file')

    def test_ruby_fileutils_rm(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileUtils.rm', 'ruby'), 'file')

    def test_ruby_http_net_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Net::HTTP.get', 'ruby'), 'http')

    def test_ruby_http_httparty(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('HTTParty.get', 'ruby'), 'http')

    def test_cpp_file_ofstream(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::ofstream', 'cpp'), 'file')

    def test_cpp_http_curl_easy_perform(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('curl_easy_perform', 'cpp'), 'http')

    def test_cpp_sleep_for(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::this_thread::sleep_for', 'cpp'), 'sleep')

    def test_cpp_log_spdlog(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('spdlog::info', 'cpp'), 'log')

    def test_hard_stop_die(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('die'), 'hard_stop')

    def test_hard_stop_exit(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('exit'), 'hard_stop')

    def test_unclassified_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('some_custom_function'))

    def test_empty_string_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call(''))

    def test_none_returns_none(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call(None))

    def test_case_insensitive(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('CURL_EXEC'), 'http')

    def test_http_setcookie(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('setcookie'), 'http')

    def test_http_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('mail'), 'http')

    def test_session_start(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_start'), 'session')

    def test_session_destroy(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_destroy'), 'session')

    def test_env_getenv(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('getenv'), 'env')

    def test_env_os_environ(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.environ'), 'env')

    def test_log_trigger_error(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('trigger_error'), 'log')

    def test_db_pdo_method(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->prepare'), 'db')

    def test_cache_apc_fetch(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('apc_fetch'), 'cache')

    def test_file_readfile(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('readfile'), 'file')


class TestClassifyCallBoundaryMatch(unittest.TestCase):
    """BACK-283: segment-boundary matching, not substring containment."""

    def test_print_header_does_not_match_header(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('printHeader'))

    def test_request_headers_does_not_match_header(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('request_headers'))

    def test_gmail_does_not_match_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('gmail'))

    def test_mailer_send_does_not_match_mail(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mailer.send'))

    def test_mylog_does_not_match_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mylog'))

    def test_my_pdo_class_does_not_match_pdo(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mypdo'))

    def test_bare_header_classifies_as_http(self):
        # Re-added in BACK-283 now that boundary matching is safe.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('header'), 'http')

    def test_php_member_call_pdo_prepare_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$pdo->prepare'), 'db')

    def test_new_pdo_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new PDO'), 'db')

    def test_nested_segment_match_services_cache_set(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('services.cache.set'), 'cache')

    def test_os_getenv_classifies_as_env_via_segment(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.getenv'), 'env')

    def test_app_logger_info_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('app.logger.info'), 'log')


class TestClassifyCallReceiver(unittest.TestCase):
    """BACK-285a: receiver-shape heuristics on non-final segments."""

    def test_cursor_execute_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('cursor.execute'), 'db')

    def test_conn_connection_receiver_no_longer_classifies_as_db(self):
        # BACK-594 (sideeffects-recall-oracle, real-corpus): `conn`/`connection`
        # were REMOVED from the language-unscoped db receiver fallback. They are
        # extremely common non-db variable names and produced corpus-confirmed
        # cross-language false positives — Go websocket `conn.Close()`/
        # `conn.Subprotocol()` -> db (client-go), Python websocket
        # `connection.send_result(...)` -> db (Home Assistant). Per the
        # conservative philosophy an ambiguous receiver is DECLINED, not guessed.
        # Real db calls formerly relying on these are now caught precisely by the
        # explicit `session.<orm-verb>` python patterns and the common
        # `->execute`/`->commit`-shaped verbs (e.g. `connection.execute`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('conn::commit'))
        self.assertIsNone(classify_call('connection.close'))
        # Go corpus false positives that motivated the removal:
        self.assertIsNone(classify_call('conn.Close', language='go'))
        self.assertIsNone(classify_call('conn.Subprotocol', language='go'))

    def test_requests_receiver_no_longer_classifies_as_http(self):
        # BACK-640 (sideeffects-recall-oracle/java): 'requests' (Python's
        # requests library alias) REMOVED from the unscoped http receiver
        # fallback — as a bare English plural noun it collided with Java's
        # `request.requests.get(i)` field access (a list field, not HTTP),
        # same class as BACK-594's conn/session/cache drop. Redundant with
        # the explicit python http patterns below (still classify correctly).
        from reveal.adapters.ast.nav_effects import classify_call
        # language='java' scopes out python's explicit 'requests.get'
        # segment pattern, isolating the receiver-fallback path (which runs
        # unconditionally regardless of language) — this is what the real
        # corpus false positive hit via `reveal ... --sideeffects` on a
        # detected-Java file.
        self.assertIsNone(classify_call('request.requests.get', language='java'))
        self.assertEqual(classify_call('requests.get', language='python'), 'http')
        self.assertEqual(classify_call('requests.post', language='python'), 'http')

    def test_underscore_log_warning_classifies_as_log(self):
        # Restoration after BACK-283: was matched by substring on 'log',
        # now matched cleanly via receiver segment.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_log.warning'), 'log')

    def test_aiohttp_get_classifies_as_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('aiohttp.get'), 'http')

    # False-positive guards (BACK-286 regression coverage).

    def test_dict_get_unclassified(self):
        # Critical: BACK-286 surfaced this. `'->get('` deleted from http
        # patterns; receiver pass must not turn `dict.get` into http either.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('dict.get'))

    def test_actual_pos_get_unclassified(self):
        # Real-world false positive: `actual_pos.get(...)` on a dict.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('actual_pos.get'))

    def test_bare_receiver_word_unclassified(self):
        # Single segment is not a method call — nothing to classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('cursor'))

    def test_final_segment_session_does_not_match(self):
        # `session` only matches as a non-final receiver. `state.session`
        # has `state` as the only non-final segment; should not classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('state.session'))

    # Deferred-to-BACK-238 (project-specific receivers, intentionally None).

    def test_evlog_emit_unclassified_universal_only(self):
        # `evlog` is project-specific; needs .reveal.yaml extension.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('evlog.emit_entry'))

    def test_tsx_get_open_position_unclassified_universal_only(self):
        # `tsx` is project-specific; needs .reveal.yaml extension.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('tsx.get_open_position'))

    # BACK-286: the deleted `->get(` / `->post(` patterns must not
    # spuriously fire on bare verb names anymore.

    def test_arbitrary_get_call_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mything.get'))

    def test_arbitrary_post_call_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('mything.post'))

    # BACK-290: SQLAlchemy `engine` as a universal db receiver.

    def test_engine_execute_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('engine.execute'), 'db')

    def test_engine_connect_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('engine.connect'), 'db')

    def test_template_engine_render_unclassified(self):
        # Non-final-segment guard: `template_engine` is its own segment and
        # should not match the bare `engine` receiver.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('template_engine.render'))

    def test_rules_engine_evaluate_unclassified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('rules_engine.evaluate'))

    # BACK-401: per-language stdlib receiver/pattern coverage (.NET BCL,
    # JVM stdlib, Go stdlib, Rust std) — previously silently unclassified.

    def test_csharp_file_exists_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('File.Exists'), 'file')

    def test_csharp_directory_createdirectory_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Directory.CreateDirectory'), 'file')

    def test_csharp_environment_getenvironmentvariable_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('Environment.GetEnvironmentVariable'), 'env'
        )

    def test_csharp_underscore_logger_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_logger.LogInformation'), 'log')

    def test_csharp_httpclient_classifies_as_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('_httpClient.GetAsync'), 'http')

    def test_java_files_exists_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Files.exists'), 'file')

    def test_java_system_getenv_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getenv'), 'env')

    def test_java_system_getproperty_classifies_as_env(self):
        # BACK-639 (sideeffects-recall-oracle/java, real-corpus measurement on
        # Elasticsearch): System.getProperty is Java's dominant env-config-read
        # idiom (JVM system properties) and was entirely unclassified — 12/13
        # real env misses in the stratified sample traced to it.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getProperty'), 'env')

    def test_java_slf4j_classifies_as_log(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('slf4j.info'), 'log')

    def test_go_os_open_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.Open'), 'file')

    def test_go_ioutil_readfile_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('ioutil.ReadFile'), 'file')

    def test_go_os_getenv_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.Getenv'), 'env')

    def test_rust_std_fs_read_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::fs::read'), 'file')

    def test_rust_std_env_var_classifies_as_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::env::var'), 'env')

    def test_rust_std_process_exit_classifies_as_hard_stop(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::process::exit'), 'hard_stop')

    def test_python_file_object_receiver_still_classifies(self):
        # 'file' as a bare receiver is intentional — the caution in the
        # taxonomy docstring is about full-pattern (not receiver-scoped)
        # matching being too broad; receiver-only matching is safe.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file.read'), 'file')

    def test_kotlin_file_writetext_classifies_as_file(self):
        # BACK-477 gap map: File(...).writeText(...) was entirely absent
        # from the taxonomy — --sideeffects saw nothing for Kotlin's
        # dominant file-write idiom.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('.writeText', language='kotlin'), 'file')
        self.assertEqual(classify_call('.appendText', language='kotlin'), 'file')
        self.assertEqual(classify_call('.readText', language='kotlin'), 'file')

    def test_kotlin_writetext_unscoped_by_language(self):
        # The pattern is Kotlin-specific; a differently-scoped call must not
        # pick it up (mirrors the Go/PHP scoping tests above).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('.writeText', language='python'))

    def test_swift_write_tofile_classifies_as_file(self):
        # BACK-477 gap map: "...".write(toFile:...) was invisible to
        # --sideeffects. classify_call only sees the callee text ('write'),
        # not the toFile: argument label, so the pattern is scoped to Swift
        # rather than added as an unscoped common pattern (a bare 'write'
        # callee is too generic in other languages to mean file I/O).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('"hello".write', language='swift'), 'file')

    def test_swift_write_unscoped_by_language(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('"hello".write', language='python'))


class TestCollectEffectsCSharpBack401(unittest.TestCase):
    """BACK-401 end-to-end: collect_effects must see C# invocation_expression
    call sites (the CALL_NODE_TYPES entry was also wrong: 'invocation' vs
    the real tree-sitter-c-sharp node kind 'invocation_expression')."""

    def setUp(self):
        code = """
        class C {
            string M(string renderNodePath) {
                var x = File.Exists(renderNodePath) ? renderNodePath : "";
                return x;
            }
        }
        """
        from tree_sitter_language_pack import get_parser
        parser = get_parser('c_sharp')
        tree = ts_parse(parser, code)
        self._root = tree_root(tree)
        lines = code.split('\n')

        def get_text(node):
            sr, sc = _zero_arg(node, 'start_position').row, _zero_arg(node, 'start_position').column
            er, ec = _zero_arg(node, 'end_position').row, _zero_arg(node, 'end_position').column
            if sr == er:
                return lines[sr][sc:ec]
            parts = [lines[sr][sc:]]
            parts.extend(lines[sr + 1:er])
            parts.append(lines[er][:ec])
            return '\n'.join(parts)
        self._get_text = get_text

    def test_file_exists_call_detected_and_classified(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        kinds = [e['kind'] for e in effects]
        self.assertIn('file', kinds)


class TestJavaEffectsBack416(unittest.TestCase):
    """BACK-416: Java method_invocation dropped the method name, so the effect
    taxonomy misattributed a filesystem write. `Files.createDirectories()` (real
    write) was seen as bare "Files" and missed; `path.resolveIndex()` (no I/O)
    was seen as bare "path" and falsely classified `file`. After the fix the
    callee is receiver-qualified and only the real write is classified."""

    def _collect(self, code, fname):
        from tree_sitter_language_pack import get_parser
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = get_parser('java')
        cb = code.encode()
        root = tree_root(ts_parse(parser, code))

        def get_text(node):
            return cb[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

        stack = [root]
        func = None
        while stack:
            n = stack.pop()
            if _zero_arg(n, 'kind') == 'method_declaration' and fname in get_text(n):
                func = n
                break
            stack.extend(n.child(i) for i in range(_zero_arg(n, 'child_count')))
        return collect_effects(func, 1, 999, get_text)

    CODE = (
        "public class Fs {\n"
        "  public Directory newDirectory(IndexSettings s, ShardPath path) {\n"
        "    final Path location = path.resolveIndex();\n"
        "    Files.createDirectories(location);\n"
        "    return newFSDirectory(location);\n"
        "  }\n"
        "}\n"
    )

    def test_real_fs_write_classified_on_files_call(self):
        effects = self._collect(self.CODE, 'newDirectory')
        file_effects = [e for e in effects if e['kind'] == 'file']
        self.assertEqual(len(file_effects), 1)
        self.assertIn('createDirectories', file_effects[0]['callee'])

    def test_path_method_not_falsely_classified(self):
        effects = self._collect(self.CODE, 'newDirectory')
        # path.resolveIndex() is not I/O — it must not be a file effect.
        path_effects = [
            e for e in effects
            if e['kind'] == 'file' and 'resolveIndex' in (e['callee'] or '')
        ]
        self.assertEqual(path_effects, [])

    def test_java_method_invocation_callee_is_receiver_qualified(self):
        from tree_sitter_language_pack import get_parser
        from reveal.adapters.ast.nav_calls import range_calls
        parser = get_parser('java')
        cb = self.CODE.encode()
        root = tree_root(ts_parse(parser, self.CODE))
        gt = lambda n: cb[_zero_arg(n, 'start_byte'):_zero_arg(n, 'end_byte')].decode()
        stack = [root]
        func = None
        while stack:
            n = stack.pop()
            if _zero_arg(n, 'kind') == 'method_declaration':
                func = n
                break
            stack.extend(n.child(i) for i in range(_zero_arg(n, 'child_count')))
        callees = [c['callee'] for c in range_calls(func, 1, 999, gt)]
        self.assertIn('Files.createDirectories', callees)
        self.assertIn('path.resolveIndex', callees)

    def test_classify_regression_matrix(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Files.createDirectories'), 'file')
        self.assertIsNone(classify_call('path.resolveIndex'))
        self.assertIsNone(classify_call('Path.Combine'))
        self.assertEqual(classify_call('file.read'), 'file')  # lowercase kept
        self.assertEqual(classify_call('fs.writeFileSync'), 'file')  # Node fs


class TestClassifyCallLanguageScoping(unittest.TestCase):
    """BACK-431 Issue D: per-language taxonomy tables, opt-in via `language=`."""

    def test_unscoped_call_matches_every_language_back_compat(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # No language given == old flat-taxonomy behavior: every language's
        # patterns still fire, so existing (unscoped) callers see no change.
        self.assertEqual(classify_call('session_start'), 'session')
        self.assertEqual(classify_call('os.mkdirall'), 'file')
        self.assertEqual(classify_call('std::process::exit'), 'hard_stop')

    def test_php_builtin_scoped_to_php_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('session_start', language='php'), 'session')
        self.assertIsNone(classify_call('session_start', language='go'))
        self.assertIsNone(classify_call('session_start', language='rust'))

    def test_go_stdlib_scoped_to_go_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.mkdirall', language='go'), 'file')
        self.assertIsNone(classify_call('os.mkdirall', language='python'))
        self.assertIsNone(classify_call('os.mkdirall', language='php'))

    def test_rust_stdlib_scoped_to_rust_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # 'std::process::exit' also matches via the common bare 'exit'
        # pattern regardless of language (see
        # test_common_patterns_fire_regardless_of_language) — 'std::env::var'
        # avoids that overlap and so demonstrates true rust-only scoping.
        self.assertEqual(classify_call('std::process::exit', language='rust'), 'hard_stop')
        self.assertEqual(classify_call('std::env::var', language='rust'), 'env')
        self.assertIsNone(classify_call('std::env::var', language='python'))
        self.assertIsNone(classify_call('std::env::var', language='java'))

    def test_python_stdlib_scoped_to_python_only(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # 'requests.get' matches for any language via the (unscoped)
        # _RECEIVER_TAXONOMY fallback — 'os.environ' isn't a receiver name,
        # so it isolates the python-only taxonomy table instead.
        self.assertEqual(classify_call('os.environ', language='python'), 'env')
        # BACK-629 (sideeffects-recall-oracle): Go's own 'os.environ' pattern
        # was added separately (real corpus idiom, os.Environ()) — this is no
        # longer isolating in the Go direction, so use rust (still absent)
        # to keep testing table isolation rather than Go's own coverage.
        self.assertIsNone(classify_call('os.environ', language='rust'))

    def test_js_group_aliases_share_one_bucket(self):
        from reveal.adapters.ast.nav_effects import classify_call
        for lang in ('javascript', 'typescript', 'tsx'):
            self.assertEqual(classify_call('setTimeout', language=lang), 'sleep')
        self.assertIsNone(classify_call('setTimeout', language='python'))

    def test_java_bucket_pattern_present_though_shadowed_by_common(self):
        from reveal.adapters.ast.nav_effects import classify_call
        # java's only distinguishing pattern ('system.getenv') is a superset
        # of the common bare 'getenv' pattern, so it already matches for
        # every language — there's no independently-observable java-only
        # case today, but the entry is still correct and harmless.
        self.assertEqual(classify_call('System.getenv', language='java'), 'env')

    def test_common_patterns_fire_regardless_of_language(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('db_query', language='go'), 'db')
        self.assertEqual(classify_call('db_query', language='php'), 'db')
        self.assertEqual(classify_call('die', language='rust'), 'hard_stop')

    def test_unknown_language_falls_back_to_common_only(self):
        # BACK-722 (Lua sideeffects-recall-oracle pre-flight): a known-but-
        # unmapped language (any language absent from _TAXONOMY_BY_LANG —
        # 'dart' still qualifies) used to silently fall back to the FULLY
        # UNSCOPED _COMPILED_ALL table, the same table language=None uses —
        # confirmed live on real Kong Lua source before the fix: ordinary
        # `table.insert(t, x)` (Lua stdlib) was classified 'db' via Python/
        # PHP's scoped bare 'insert' verb leaking through this fallback.
        # Fixed: an unmapped-but-named language now scopes to COMMON only
        # (its real, intended scope until it gets its own entry) — the PHP-
        # only 'session_start' pattern (not in COMMON) no longer leaks into
        # a Dart file, mirroring how any other cross-language leak (Go
        # tagged 'session' by a PHP builtin) was already prevented for
        # every language that DOES have its own entry.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='dart'))
        # True unscoped mode (language genuinely omitted) is unaffected —
        # this is the one case where matching every language's patterns is
        # the documented, intended behavior.
        self.assertEqual(classify_call('session_start', language=None), 'session')

    def test_lua_stdlib_calls_not_misclassified_via_unscoped_leak(self):
        """BACK-722: the same fallback bug, concrete real-corpus evidence.
        `table.insert`/`table.remove` (Lua's stdlib array mutators, ~80/4
        corpus call sites in Kong) and bare `select` (Lua's builtin vararg
        helper, `select('#', ...)`) were all silently classified 'db' via
        Python/PHP's scoped bare 'insert'/'select' verbs leaking through
        the old fully-unscoped fallback -- confirmed live before the fix
        with `reveal <file> <func> --sideeffects` on a Lua file containing
        nothing but `table.insert(t, x)` and `select('#', x)`."""
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('table.insert', language='lua'))
        self.assertIsNone(classify_call('table.remove', language='lua'))
        self.assertIsNone(classify_call('select', language='lua'))

    def test_go_klog_glog_logrus_classified_as_log(self):
        # BACK-629 (sideeffects-recall-oracle, real-corpus measurement on
        # k8s.io/client-go): klog.Fatalf(...) in the azure auth plugin's
        # init() was silently unclassified — 'klog' tokenizes to its own
        # segment, distinct from the common bare 'log' pattern.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('klog.Fatalf', language='go'), 'log')
        self.assertEqual(classify_call('klog.Infof', language='go'), 'log')
        self.assertEqual(classify_call('glog.Warningf', language='go'), 'log')
        self.assertEqual(classify_call('logrus.Error', language='go'), 'log')
        self.assertIsNone(classify_call('klog.Fatalf', language='python'))

    def test_go_http_stdlib_and_roundtrip_classified_as_http(self):
        # BACK-629: Go had no http bucket at all — real corpus misses on
        # client-go included `rt.RoundTrip(req)` (transport.go) and
        # `http.NewRequestWithContext(...)` (remotecommand/websocket.go).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('http.Get', language='go'), 'http')
        self.assertEqual(classify_call('http.NewRequestWithContext', language='go'), 'http')
        self.assertEqual(classify_call('rt.RoundTrip', language='go'), 'http')
        self.assertEqual(classify_call('transport.RoundTrip', language='go'), 'http')
        self.assertIsNone(classify_call('http.Get', language='python'))

    def test_go_do_call_stays_unclassified_ambiguous_verb(self):
        # `client.Do(req)` (net/http's dominant call-site idiom, e.g.
        # rest/request.go:Watch and rest/fake/fake.go:do in client-go) is
        # deliberately left unclassified: classify_call only sees the callee
        # text, not the argument, so a bare 'do' pattern would be exactly the
        # collision-prone-verb case the module docstring warns about (same
        # shape as '.save'/'.where' staying unclassified elsewhere) —
        # confirmed via the sideeffects-recall-oracle measurement loop.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('client.Do', language='go'))

    def test_go_os_lookupenv_setenv_unsetenv_environ_classified_as_env(self):
        # BACK-629: os.LookupEnv(...) in client-go's feature-gate reader
        # (features/envvar.go) was silently unclassified — only bare
        # 'getenv'/'putenv' existed in _TAXONOMY_COMMON.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.LookupEnv', language='go'), 'env')
        self.assertEqual(classify_call('os.Setenv', language='go'), 'env')
        self.assertEqual(classify_call('os.Unsetenv', language='go'), 'env')
        self.assertEqual(classify_call('os.Environ', language='go'), 'env')
        self.assertIsNone(classify_call('os.LookupEnv', language='python'))

    def test_python_os_remove_makedirs_classified_as_file(self):
        # BACK-634 (sideeffects-recall-oracle/python, real-corpus measurement
        # on Home Assistant): os.remove / os.makedirs — the exact stdlib twins
        # of the already-present os.unlink / os.mkdir — were silently
        # unclassified. Real corpus misses: `os.remove(filename)`
        # (nest/media_source.py:async_remove_media, verisure/camera.py) and
        # `os.makedirs(...)` (helpers/storage.py, knx/telegrams.py).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('os.remove', language='python'), 'file')
        self.assertEqual(classify_call('os.makedirs', language='python'), 'file')

    def test_python_pathlib_read_write_methods_classified_as_file(self):
        # BACK-634: pathlib's file-I/O methods are invoked on Path *values*
        # (`self._path.write_text(...)`, `file_path.read_bytes()`), so the
        # 'pathlib' module pattern never matched them. Same shape BACK-477
        # added for Kotlin's kotlin.io writeText/readText/writeBytes/readBytes.
        # Real misses: `self._path.write_text(ics_content)`
        # (local_calendar/store.py), `file_path.read_bytes()` (llama_cpp).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('self._path.write_text', language='python'), 'file')
        self.assertEqual(classify_call('file_path.read_bytes', language='python'), 'file')
        self.assertEqual(classify_call('p.read_text', language='python'), 'file')
        self.assertEqual(classify_call('out.write_bytes', language='python'), 'file')

    def test_python_async_get_clientsession_stays_unclassified_project_idiom(self):
        # BACK-634 deliberate non-fix: `async_get_clientsession(hass)` is Home
        # Assistant's dominant HTTP-client factory and the single largest http
        # recall gap in the corpus — but it is a PROJECT-specific helper name,
        # not a Python/stdlib idiom. Per the module docstring, project-specific
        # names belong in a `.reveal.yaml` extension (BACK-238), not the global
        # taxonomy (the same reasoning that keeps Go's `client.Do` unclassified).
        # Genuinely global http idioms in the corpus (requests.get/delete,
        # aiohttp.ClientSession) are already classified.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('async_get_clientsession', language='python'))
        self.assertIsNone(
            classify_call('aiohttp_client.async_get_clientsession', language='python'))
        self.assertEqual(classify_call('requests.get', language='python'), 'http')

    # ── BACK-635: bare-verb subsequence over-fire (fail-before / pass-after) ──

    def test_python_dict_update_not_db(self):
        # `->update` was moved to PHP-only. The tokenizer strips the arrow, so
        # it used to collapse to bare `update` and tag every Python `.update()`
        # as db (corpus: 12 FPs on Home Assistant incl. 2/60 negative-control
        # FPs `added_doors.update(...)` / `self.data.update()`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('domains.update', language='python'))
        self.assertIsNone(classify_call('added_doors.update', language='python'))
        self.assertIsNone(classify_call('self.data.update', language='python'))
        self.assertIsNone(classify_call('device.update', language='python'))

    def test_python_value_copy_not_file(self):
        # bare `copy` was moved to PHP-only (PHP's `copy()` builtin). It used to
        # tag every value-copy idiom as file (corpus: 4 FPs — `entry.data.copy()`,
        # `os.environ.copy()`, `env.copy()`).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('x.copy', language='python'))
        self.assertIsNone(classify_call('entry.data.copy', language='python'))
        # `os.environ.copy()` is now correctly ENV (via the os.environ pattern),
        # no longer mislabeled file by the bare `copy` verb.
        self.assertEqual(classify_call('os.environ.copy', language='python'), 'env')

    def test_python_requests_delete_is_http_not_db(self):
        # `->delete` was moved to PHP-only. It used to collapse to bare `delete`
        # and — because kind-order puts db before http — STEAL Python's explicit
        # `requests.delete` -> http, mislabeling it db (corpus: itunes/_request).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('requests.delete', language='python'), 'http')

    def test_php_arrow_db_and_copy_still_classify(self):
        # Proof the BACK-635 fix SCOPED rather than deleted these patterns: the
        # PHP idioms they legitimately serve must still classify.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$model->update', language='php'), 'db')
        self.assertEqual(classify_call('$repo->delete', language='php'), 'db')
        self.assertEqual(classify_call('copy', language='php'), 'file')
        # Unscoped (no language) also still classifies — every language's
        # patterns merge, so back-compat callers see the PHP idiom too.
        self.assertEqual(classify_call('$model->update'), 'db')
        self.assertEqual(classify_call('copy'), 'file')

    def test_cpp_fileaccess_idiom_classified_as_file(self):
        # BACK-547 fourth language (sideeffects-recall-oracle, real-corpus
        # measurement on Godot's core/): a cross-platform-engine codebase
        # almost never calls stdlib ofstream/fopen directly — real corpus
        # misses were FileAccess::open(...) (static factory) and instance
        # calls like f->store_line(...)/f->get_buffer(...), none of which
        # matched the generic-stdlib-only 'file' patterns already present.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileAccess::open', language='cpp'), 'file')
        self.assertEqual(classify_call('f->store_line', language='cpp'), 'file')
        self.assertEqual(classify_call('f->store_buffer', language='cpp'), 'file')
        self.assertEqual(classify_call('f->get_buffer', language='cpp'), 'file')
        self.assertIsNone(classify_call('f->store_line', language='python'))

    def test_cpp_os_singleton_env_and_sleep_wrapper_classified(self):
        # BACK-547 fourth language: bare 'getenv'/'putenv' (_TAXONOMY_COMMON)
        # never matches the cross-platform-engine OS-singleton wrapper idiom
        # (`OS::get_singleton()->get_environment(...)`/`->delay_usec(...)`) —
        # real corpus misses: core_bind.cpp:OS::get_environment/
        # set_environment/has_environment/unset_environment/delay_usec/
        # delay_msec.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS::get_singleton()->get_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->has_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->set_environment', language='cpp'), 'env')
        self.assertEqual(classify_call('OS::get_singleton()->delay_usec', language='cpp'), 'sleep')
        self.assertEqual(classify_call('OS::get_singleton()->delay_msec', language='cpp'), 'sleep')

    def test_cpp_print_line_and_warn_err_print_classified_as_log(self):
        # BACK-547 fourth language: print_line/print_error/print_verbose and
        # the WARN_PRINT/ERR_PRINT macros are the dominant logging idiom in
        # engine code built this way (same shape as Go's klog/glog/logrus
        # addition, BACK-629) — real corpus misses across config/engine.cpp,
        # object/message_queue.cpp, and elsewhere.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('print_line', language='cpp'), 'log')
        self.assertEqual(classify_call('print_error', language='cpp'), 'log')
        self.assertEqual(classify_call('print_verbose', language='cpp'), 'log')
        self.assertEqual(classify_call('WARN_PRINT', language='cpp'), 'log')
        self.assertEqual(classify_call('ERR_PRINT', language='cpp'), 'log')
        self.assertIsNone(classify_call('print_line', language='python'))

    # ── BACK-594: receiver fallback crossing language boundaries ──

    def test_python_session_receiver_not_db_for_http_verbs(self):
        # `session`/`connection` were dropped from the receiver fallback. aiohttp
        # `session.get(url)`, OAuth `session.async_ensure_token_valid()`, and
        # websocket `connection.send_result(...)` used to be tagged db purely by
        # the receiver name (corpus: 9 occurrences on Home Assistant).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session.async_ensure_token_valid', language='python'))
        self.assertIsNone(classify_call('session.async_on_cleanup', language='python'))
        self.assertIsNone(classify_call('connection.send_result', language='python'))
        self.assertIsNone(classify_call('connection.send_error', language='python'))
        # `session.get` is genuinely ambiguous (aiohttp http vs SQLAlchemy 2.0
        # db read) -> DECLINED, not guessed.
        self.assertIsNone(classify_call('session.get', language='python'))

    def test_python_sqlalchemy_session_orm_verbs_still_db(self):
        # Recall guard: the real SQLAlchemy db calls that used to rely on the
        # dropped `session` receiver are now caught by explicit python patterns,
        # so db recall does not regress (verified 25/25 on the oracle).
        from reveal.adapters.ast.nav_effects import classify_call
        for verb in ('add', 'flush', 'commit', 'rollback', 'refresh',
                     'expunge', 'expunge_all', 'merge', 'connection', 'scalars'):
            self.assertEqual(
                classify_call(f'session.{verb}', language='python'), 'db',
                msg=f'session.{verb} should classify as db')
        # cursor / bare-verb paths still work too.
        self.assertEqual(classify_call('cursor.execute', language='python'), 'db')
        self.assertEqual(classify_call('session.query', language='python'), 'db')
        self.assertEqual(classify_call('connection.execute', language='python'), 'db')

    def test_go_cache_receiver_not_cache(self):
        # BACK-594: bare `cache` receiver dropped — `k8s.io/client-go/tools/cache`
        # is a package literally named `cache`, so `cache.NewListWatchFromClient`
        # was mislabeled a cache side effect. redis/memcache receivers are kept.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('cache.NewListWatchFromClient', language='go'))
        self.assertIsNone(classify_call('cache.NewIndexer', language='go'))


class TestTypeScriptEffectsBack547(unittest.TestCase):
    """BACK-547 fifth language (sideeffects-recall-oracle, TypeScript/VS Code
    corpus, 65,008 functions). Pre-flight check (following the C++ loop's own
    carried-forward note) found a real collision before any oracle code was
    written: bare 'fetch' matched via _TAXONOMY_COMMON's `->fetch` (a bare
    verb kept common for PHP's `$stmt->fetch()`/Python DB-API recall) beat
    js's own explicit http 'fetch(' entry, because db precedes http in
    _KIND_ORDER — every JS/TS global `fetch()` HTTP call silently classified
    as db instead."""

    def test_js_bare_fetch_classifies_as_http_not_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('fetch', language='typescript'), 'http')
        self.assertEqual(classify_call('fetch', language='javascript'), 'http')

    def test_php_arrow_fetch_still_classifies_as_db(self):
        # ->fetch moved from _TAXONOMY_COMMON to _TAXONOMY_BY_LANG['php'] —
        # PHP's $stmt->fetch() (PDOStatement/mysqli_result row fetch) must
        # keep working, scoped or unscoped.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('$stmt->fetch', language='php'), 'db')
        self.assertEqual(classify_call('$stmt->fetch'), 'db')  # unscoped

    def test_bare_fetch_no_longer_db_for_other_languages(self):
        # Corpus-confirmed (samples/python): bare `.fetch(` has zero real
        # occurrences in Python — only PHP genuinely needs it.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('fetch', language='python'))
        self.assertIsNone(classify_call('fetch', language='go'))

    def test_js_indexeddb_classified_as_db(self):
        # Real corpus miss: indexedDB.deleteDatabase(database.name) in
        # src/vs/base/browser/indexedDB.ts:deleteDatabase — js had no db
        # bucket at all before this loop.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('indexedDB.deleteDatabase', language='typescript'), 'db')
        self.assertEqual(classify_call('indexedDB.open', language='typescript'), 'db')
        self.assertEqual(classify_call('db.createObjectStore', language='typescript'), 'db')
        self.assertIsNone(classify_call('indexedDB.deleteDatabase', language='python'))

    def test_js_node_http_stdlib_classified_as_http(self):
        # Real corpus miss: https.get(requestOptions, ...) in
        # extensions/vscode-test-resolver/src/download.ts:
        # downloadVSCodeServerArchive.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('https.get', language='typescript'), 'http')
        self.assertEqual(classify_call('http.get', language='typescript'), 'http')
        self.assertEqual(classify_call('https.request', language='typescript'), 'http')
        self.assertEqual(classify_call('http.request', language='typescript'), 'http')

    def test_js_request_service_wrapper_declined_project_specific(self):
        # VS Code's own `requestService.request(...)` internal abstraction
        # (3 real corpus misses: abstractUpdateService.ts:isLatestVersion,
        # updateService.linux.ts:doCheckForUpdates,
        # userDataProfileInit.ts:doGetProfileTemplate) is deliberately NOT
        # added — a single-repo internal wrapper name, same declined shape
        # as Python's async_get_clientsession (BACK-634) and Go's client.Do
        # (BACK-633).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('requestService.request', language='typescript'))

    def test_js_process_env_stays_unclassified_by_the_call_channel(self):
        # BACK-644: process.env.FOO is a property/subscript access, never a
        # call_expression, so range_calls() never extracts it as a callee and
        # classify_call() can never see it — a call-taxonomy entry for it would
        # be dead code (verified: 0/26 real corpus hits with the pattern
        # present). Still deliberately NOT added: env classification for JS/TS
        # is now real, but it lives in collect_effects()'s property channel
        # (test_process_env_read_is_classified_env below), not here.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('process.env', language='typescript'))

    def test_process_env_read_is_classified_env(self):
        # BACK-644 (fixed), end-to-end: a function whose ONLY effect is a
        # process.env property read produces zero *call* sites, so this is
        # exactly the shape that was invisible before the property channel
        # existed. Both the dotted and subscript forms must be classified, and
        # rendered WITHOUT a `()` suffix — they are not calls.
        from reveal.adapters.ast.nav_effects import collect_effects, render_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function readToken() {
            const token = process.env.MY_TOKEN;
            const other = process.env['SECRET'];
            return token + other;
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual(
            [(e['line'], e['kind'], e['callee'], e['via']) for e in effects],
            [(2, 'env', 'process.env.MY_TOKEN', 'property'),
             (3, 'env', "process.env['SECRET']", 'property')],
        )
        rendered = render_effects(effects, 1, 999)
        self.assertIn('process.env.MY_TOKEN', rendered)
        self.assertNotIn('process.env.MY_TOKEN()', rendered)

    def test_process_env_method_call_is_not_double_reported(self):
        # BACK-644: `os.environ.get('X')` is classified 'env' by the CALL
        # channel, and its callee `os.environ.get` is an attribute whose base
        # text is exactly `os.environ` — so without callee suppression the
        # property channel would report the same env access a second time on
        # the same line. Exactly one effect per line is the contract.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('python')
        src = textwrap.dedent("""
        def f():
            a = os.environ.get('CALL_FORM')
            b = os.environ['SUBSCRIPT_FORM']
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='python')
        self.assertEqual(
            [(e['line'], e['kind'], e['via']) for e in effects],
            [(2, 'env', 'call'), (3, 'env', 'property')],
        )

    def test_ruby_env_constant_matches_but_rack_env_local_does_not(self):
        # BACK-644, the precision trap this channel exists to avoid: Ruby's
        # `ENV['X']` is the process environment, but `env['X']` is Rack's
        # request hash — 199 of them in Discourse against 534 real ENV[ reads.
        # classify_call()'s _tokenize() lowercases and so cannot tell them
        # apart; the property channel matches base text CASE-SENSITIVELY.
        # Also covers `ENV['X'].blank?`, where Ruby's `call` exposes the
        # element_reference as its RECEIVER (child(0)) rather than a callee —
        # suppressing child(0) generically would lose the read entirely.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('ruby')
        src = textwrap.dedent("""
        def handle(env)
          real = ENV['SECRET_KEY']
          guarded = ENV['HOME'].blank?
          rack = env['HTTP_HOST']
          more = env.fetch('REQUEST_METHOD')
        end
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='ruby')
        self.assertEqual(
            [(e['line'], e['kind'], e['callee']) for e in effects if e['kind'] == 'env'],
            [(2, 'env', "ENV['SECRET_KEY']"), (3, 'env', "ENV['HOME']")],
        )

    def test_property_channel_ignores_lookalike_bases(self):
        # BACK-644: the channel matches an explicit base allowlist, never a
        # "member access = effect" shape — a wrong classification is worse than
        # an unclassified read. `config.process.env.X` (a local object, real:
        # VS Code's terminalSandboxEngine.test.ts) and a bare `process.env`
        # passed around without reading a key are both correctly not env.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function f(config) {
            const a = config.process.env.FOO;
            const b = other.env.BAR;
            spawn(cmd, process.env);
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual([e for e in effects if e['kind'] == 'env'], [])

    def test_property_channel_keeps_receiver_of_a_method_call(self):
        # BACK-644: only the callee node itself is suppressed, never its
        # subtree — in `process.env.FOO.trim()` the receiver `process.env.FOO`
        # is a real env read and must survive.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('typescript')
        src = textwrap.dedent("""
        function f() {
            return process.env.FOO.trim();
        }
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='typescript')
        self.assertEqual(
            [(e['kind'], e['callee']) for e in effects if e['kind'] == 'env'],
            [('env', 'process.env.FOO')],
        )


class TestCollectEffects(unittest.TestCase):

    def setUp(self):
        code = """\
<?php
function processOrder($order_id) {
    $sql = mysql_query("SELECT * FROM orders WHERE id=" . $order_id);
    if (!$sql) {
        error_log("DB failed");
        die("fatal");
    }
    curl_exec(curl_init("https://api.example.com"));
    sleep(1);
    return mysql_fetch_assoc($sql);
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _effects(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        return collect_effects(self._root, 1, 999, self._get_text)

    def test_returns_list(self):
        self.assertIsInstance(self._effects(), list)

    def test_effects_have_required_fields(self):
        effects = self._effects()
        for e in effects:
            self.assertIn('line', e)
            self.assertIn('callee', e)
            self.assertIn('kind', e)

    def test_db_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('db', kinds)

    def test_http_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('http', kinds)

    def test_log_calls_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('log', kinds)

    def test_hard_stop_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('hard_stop', kinds)

    def test_sleep_found(self):
        effects = self._effects()
        kinds = [e['kind'] for e in effects]
        self.assertIn('sleep', kinds)

    def test_sorted_by_line(self):
        effects = self._effects()
        classified = [e for e in effects if e['kind'] is not None]
        lines = [e['line'] for e in classified]
        self.assertEqual(lines, sorted(lines))

    def test_range_filtering(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        # Only lines 3-4 — should find mysql_query but not die/curl_exec
        effects = collect_effects(self._root, 3, 4, self._get_text)
        callees = [e['callee'] for e in effects if e['kind'] is not None]
        self.assertTrue(any('mysql_query' in (c or '') for c in callees))
        self.assertFalse(any('die' in (c or '') for c in callees))


class TestPhpMemberAndObjectCalls(unittest.TestCase):
    """BACK-284: range_calls must detect PHP $obj->method() and new X()."""

    def setUp(self):
        code = """\
<?php
function audit_db() {
    $dsn = getenv('DB_DSN');
    $pdo = new PDO($dsn);
    $stmt = $pdo->prepare("SELECT * FROM users");
    $stmt->execute();
    $row = $stmt->fetch();
    return $row;
}
"""
        self._tree, self._root, self._get_text, _ = _parse_php(code)

    def _calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        return range_calls(self._root, 1, 999, self._get_text)

    def test_object_creation_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('new PDO', callees)

    def test_member_call_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('$pdo->prepare', callees)
        self.assertIn('$stmt->execute', callees)
        self.assertIn('$stmt->fetch', callees)

    def test_bare_function_still_detected(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertIn('getenv', callees)

    def test_all_five_calls_present(self):
        callees = [c['callee'] for c in self._calls()]
        self.assertEqual(len(callees), 5)

    def test_object_creation_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        new_pdo = next((e for e in effects if e['callee'] == 'new PDO'), None)
        self.assertIsNotNone(new_pdo)
        self.assertEqual(new_pdo['kind'], 'db')

    def test_member_call_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        effects = collect_effects(self._root, 1, 999, self._get_text)
        kinds_by_callee = {e['callee']: e['kind'] for e in effects}
        self.assertEqual(kinds_by_callee.get('$stmt->execute'), 'db')
        self.assertEqual(kinds_by_callee.get('$stmt->fetch'), 'db')


class TestRenderEffects(unittest.TestCase):

    def _make_effects(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        code = """\
<?php
function f() {
    mysql_query("SELECT 1");
    error_log("x");
    die("stop");
}
"""
        _, root, get_text, _ = _parse_php(code)
        return collect_effects(root, 1, 999, get_text)

    def test_output_is_string(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIsInstance(result, str)

    def test_output_contains_kind_labels(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIn('db', result)
        self.assertIn('log', result)
        self.assertIn('hard_stop', result)

    def test_output_contains_line_numbers(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects(self._make_effects(), 1, 999)
        self.assertIn('L3', result)

    def test_empty_effects_returns_message(self):
        from reveal.adapters.ast.nav_effects import render_effects
        result = render_effects([], 1, 999)
        self.assertIn('No classified side effects', result)


# ---------------------------------------------------------------------------
# BACK-203: PHP varflow — variable_name node type fix
# ---------------------------------------------------------------------------

class TestBack724GdscriptTaxonomy(unittest.TestCase):
    """BACK-718/BACK-724 (GDScript, seventeenth side-effect-recall language,
    corpus: Pixelorama samples/gdscript_pixelorama, a real production Godot 4
    pixel-art editor). GDScript had zero _TAXONOMY_BY_LANG entries before this
    loop; scoped to language='gdscript' so none of these can fire
    cross-language. All patterns corpus-grounded and corpus-collision-checked
    (scripts/check_taxonomy_collisions.py)."""

    def test_fileaccess_diraccess_classified_file(self):
        # Godot 4's FileAccess/DirAccess static-factory API -- dotted,
        # scoped two-segment (same shape as Dart's http.get/Zig's
        # io.connect entries).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileAccess.open', language='gdscript'), 'file')
        self.assertEqual(classify_call('FileAccess.file_exists', language='gdscript'), 'file')
        self.assertEqual(classify_call('DirAccess.open', language='gdscript'), 'file')
        self.assertEqual(classify_call('DirAccess.remove_absolute', language='gdscript'), 'file')

    def test_fileaccess_instance_methods_bare_verbs_classified_file(self):
        # FileAccess/StreamPeer instance methods -- bare verbs, since the
        # receiver is a local var holding FileAccess.open(...)'s return
        # (`file`, `ase_file`, `palette_file`, ... -- no fixed name to scope
        # a dotted pattern against).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('file.store_line', language='gdscript'), 'file')
        self.assertEqual(classify_call('ase_file.get_buffer', language='gdscript'), 'file')
        self.assertEqual(classify_call('palette_file.store_var', language='gdscript'), 'file')
        self.assertEqual(classify_call('import_file.get_as_text', language='gdscript'), 'file')

    def test_os_environment_classified_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS.get_environment', language='gdscript'), 'env')
        self.assertEqual(classify_call('OS.set_environment', language='gdscript'), 'env')
        self.assertEqual(classify_call('OS.has_environment', language='gdscript'), 'env')

    def test_push_error_warning_printerr_classified_log_not_bare_print(self):
        # push_error/push_warning/printerr/print_rich -- bare verbs (GDScript's
        # print family is always called receiverless), corpus-collision-check
        # came back clean (the only non-zero cross-language hits are Godot's
        # OWN C++ engine implementation of these exact builtins). Bare 'print'
        # itself was TRIED AND DECLINED -- same catastrophic-collision class
        # as the Swift loop's declined bare print (SWIFT.md).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('push_error', language='gdscript'), 'log')
        self.assertEqual(classify_call('push_warning', language='gdscript'), 'log')
        self.assertEqual(classify_call('printerr', language='gdscript'), 'log')
        self.assertEqual(classify_call('print_rich', language='gdscript'), 'log')
        self.assertIsNone(classify_call('print', language='gdscript'))

    def test_os_delay_and_create_timer_classified_sleep(self):
        # OS.delay_msec/delay_usec (blocking) and bare 'create_timer' (the
        # `get_tree().create_timer(...).timeout` non-blocking idiom -- no
        # fixed receiver to scope narrower against, same shape as the file
        # bucket's bare store_*/get_* verbs).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('OS.delay_msec', language='gdscript'), 'sleep')
        self.assertEqual(classify_call('OS.delay_usec', language='gdscript'), 'sleep')
        self.assertEqual(classify_call('get_tree().create_timer', language='gdscript'), 'sleep')

    def test_bare_request_declined_for_http(self):
        # TRIED AND DECLINED: bare 'request' -- the only verb the corpus's
        # real HTTPRequest.request(...) call sites share -- has catastrophic
        # cross-language collision (java 785 hits, php 422, lua 308, ...) in
        # classify_call's unscoped fallback mode. GDScript's 'http' bucket
        # has no entries this loop; verify it stays unclassified rather than
        # silently matching some future addition.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('http_request.request', language='gdscript'))

    def test_gdscript_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop gdscript had no _TAXONOMY_BY_LANG
        # entry at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's
        # fix, whose own comment names gdscript explicitly as one of the
        # exposed-but-unmeasured languages). A Python/PHP-only builtin must
        # still never leak into a GDScript file.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='gdscript'))
        self.assertIsNone(classify_call('$wpdb', language='gdscript'))


class TestBack726TsxTaxonomy(unittest.TestCase):
    """BACK-718/BACK-726 real-corpus taxonomy fixes (samples/tsx/excalidraw,
    a real production React/TSX drawing app, 292 .tsx/.jsx files)."""

    def test_console_info_debug_trace_classified_log(self):
        # Real miss: examples/with-script-in-browser/components/
        # ExampleApp.tsx calls `console.info("Elements :", ...)` twice,
        # unclassified before this fix (only console.log/error/warn existed).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('console.info', 'tsx'), 'log')
        self.assertEqual(classify_call('console.debug', 'tsx'), 'log')
        self.assertEqual(classify_call('console.trace', 'tsx'), 'log')

    def test_localstorage_classified_db(self):
        # Real misses: excalidraw-app/components/DebugCanvas.tsx
        # (localStorage.setItem/getItem), excalidraw-app/
        # ExcalidrawPlusIframeExport.tsx (localStorage.getItem),
        # excalidraw-app/components/TopErrorBoundary.tsx
        # (localStorage.clear) -- 5 real non-test call sites, entirely
        # unclassified before this fix (only IndexedDB existed in 'db').
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('localStorage.getItem', 'tsx'), 'db')
        self.assertEqual(classify_call('localStorage.setItem', 'jsx'), 'db')
        self.assertEqual(classify_call('localStorage.clear', 'javascript'), 'db')

    def test_window_open_bare_verb_collision_declined_not_fixed(self):
        """Corroborating finding, NOT a fix: `window.open(...)` (opens a
        browser tab, a UI-navigation action) and `this.portal.open(...)`
        (opens a socket.io connection) both fire _TAXONOMY_COMMON's
        pre-existing bare 'open(' pattern and get tagged 'file' -- a false
        positive, corpus-confirmed on excalidraw-app/App.tsx:ExcalidrawWrapper
        and excalidraw-app/collab/Collab.tsx:startCollaboration. Same shape
        and same verdict as every prior loop's declined bare-verb collision
        (Zig's 'open'/'header' on TigerBeetle's own accessor methods, Go's
        declined 'Do'): _TAXONOMY_COMMON-scoped, cross-language blast radius,
        out of scope for a single-language loop to narrow. This test locks in
        the CURRENT (not-yet-fixed) behavior so a future narrowing of the
        common 'open(' pattern is a deliberate, reviewed change, not a
        silent regression of this loop's own findings."""
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('window.open', 'tsx'), 'file')


class TestBack728SwiftSixCategoryWidening(unittest.TestCase):
    """BACK-728: deepened Swift past its http-only sideeffects-recall-oracle
    sample (BACK-547 eleventh/final loop) to the full six-category sweep,
    widening the corpus scope from samples/swift/KsApi/Sources/KsApi
    (328 files) to the whole samples/swift tree (Kickstarter iOS, 2,051
    files). Recall: 43.33% (26/60, pre-widening taxonomy already in place)
    -> 100.00% (60/60), 0 negative-sample false positives, 0 functions with
    an extra kind, at both measurements. See SWIFT.md for the full corpus
    survey and per-finding writeup."""

    def test_keychain_security_framework_classified_db(self):
        # Kickstarter's OAuth-token storage wraps the Security framework's
        # raw C API (Library/Sources/Library/Library/Keychain.swift) --
        # SecItemAdd/SecItemUpdate/SecItemDelete/SecItemCopyMatching are
        # bare, receiverless calls; callers reach the wrapper via a dotted
        # Keychain.<verb> receiver (AppEnvironment.swift). Both forms,
        # zero cross-language collision risk (Apple Security-framework /
        # project-specific type names).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('SecItemAdd', language='swift'), 'db')
        self.assertEqual(classify_call('SecItemCopyMatching', language='swift'), 'db')
        self.assertEqual(
            classify_call('Keychain.storePassword', language='swift'), 'db',
        )
        self.assertEqual(
            classify_call('Keychain.fetchPassword', language='swift'), 'db',
        )

    def test_userdefaults_classified_db(self):
        # UserDefaults/userDefaults local key-value persistence -- same
        # category TSX/JS's own loop already classifies browser
        # localStorage as (BACK-718/BACK-726). Two-segment
        # `userdefaults.set`/`.dictionary` cover AppEnvironment.swift's
        # saveEnvironment/fromStorage; the three-segment
        # `UserDefaults.standard.register(defaults:...)` (Service.swift)
        # needs its own exact entry since sliding-window matching requires
        # CONSECUTIVE segments and `standard` sits between `userdefaults`
        # and `register`.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('userDefaults.set', language='swift'), 'db',
        )
        self.assertEqual(
            classify_call('userDefaults.dictionary', language='swift'), 'db',
        )
        self.assertEqual(
            classify_call('UserDefaults.standard.register', language='swift'), 'db',
        )

    def test_filemanager_moveitem_classified_file(self):
        # FileManager.default.moveItem(at:to:) -- RichPushNotifications/
        # NotificationService.swift's push-notification-attachment handling,
        # the widened corpus's one real non-`write` file idiom. Exact
        # three-segment match (a bare `moveitem`/`filemanager` heuristic
        # would be corpus-unsafe -- FileManager is a common enough receiver
        # name elsewhere in this same corpus and others).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('FileManager.default.moveItem', language='swift'), 'file',
        )

    def test_downloadtask_classified_http(self):
        # session.downloadTask(with:completionHandler:) -- URLSession's
        # download-to-disk sibling of dataTask (already classified);
        # RichPushNotifications/NotificationService.swift's only remaining
        # miss after the other five fixes.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('session.downloadTask', language='swift'), 'http',
        )

    def test_bundle_main_infodictionary_classified_env(self):
        # Bundle.main.infoDictionary -- ServiceType.userAgent's app-version/
        # bundle-metadata read, MFMailComposeViewController.support's
        # support-email diagnostics. Renders as an ordinary extractable
        # callee (the optional-subscript access `Bundle.main
        # .infoDictionary?[...]` is call-shaped in this grammar), so an
        # ordinary three-segment _TAXONOMY_BY_LANG entry reaches it directly
        # -- no BACK-644/BACK-727-style property-access channel needed.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('Bundle.main.infoDictionary', language='swift'), 'env',
        )

    def test_crashlytics_factory_call_classified_log(self):
        # Crashlytics.crashlytics().log(format:...) / .record(error:...) --
        # Kickstarter's crash-reporting/log idiom (AppEnvironment.swift,
        # OAuth.swift, AppDelegate.swift). nav_calls' fluent-chain callee
        # collapse means classify_call() only ever sees the bare final verb
        # (`log`/`record`) for the CHAINED call -- bare `record` is too
        # generic to classify safely on its own. Matching the
        # `Crashlytics.crashlytics` FACTORY call instead (its own distinct,
        # separately-visible call node) captures every real corpus site
        # through one precise, zero-cross-language-collision pattern.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('Crashlytics.crashlytics', language='swift'), 'log',
        )
        self.assertIsNone(classify_call('record', language='swift'))

    def test_dispatchqueue_asyncafter_classified_sleep(self):
        # DispatchQueue.<queue>.asyncAfter(deadline:...) -- GCD's
        # callback-based timer, this corpus's dominant non-test sleep idiom
        # (5 real sites across UIRefreshControl+StartRefreshing.swift,
        # MessageBannerView.swift, VideoFeedToastContainerView.swift,
        # VideoFeedVideoPlayer.swift, AppDelegate.swift). Bare (not
        # receiver-scoped) since the queue varies (.main/.global()/custom);
        # Task.sleep already recalled via the pre-existing common bare
        # 'sleep' pattern before this loop, unchanged here.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('DispatchQueue.main.asyncAfter', language='swift'), 'sleep',
        )
        self.assertEqual(classify_call('Task.sleep', language='swift'), 'sleep')

    def test_prior_http_apollo_taxonomy_unregressed(self):
        # The original loop's Apollo GraphQL fetch/perform/*WithResult/
        # dataTask entries (BACK-547 eleventh loop, TestBack547Swift
        # ApolloHttpTaxonomy) must stay intact through this widening --
        # spot-checked here as a regression guard alongside that class's
        # own full coverage.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('client.fetch', language='swift'), 'http')
        self.assertEqual(classify_call('client.perform', language='swift'), 'http')


class TestBack547RubyDbAndFileTaxonomy(unittest.TestCase):
    def _sideeffect_kinds(self, src):
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('ruby')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='ruby')
        return {e['kind'] for e in effects}

    def test_activerecord_where_classified_as_db(self):
        kinds = self._sideeffect_kinds(
            "def find_active\n"
            "  User.where(active: true)\n"
            "end\n"
        )
        self.assertIn('db', kinds)

    def test_activerecord_pluck_and_delete_all_classified_as_db(self):
        kinds = self._sideeffect_kinds(
            "def purge\n"
            "  ids = posts.pluck(:id)\n"
            "  Notification.where(post_id: ids).delete_all\n"
            "end\n"
        )
        self.assertIn('db', kinds)

    def test_fileutils_rm_f_and_rm_rf_classified_as_file(self):
        kinds = self._sideeffect_kinds(
            "def stop\n"
            "  FileUtils.rm_f(@socket_path)\n"
            "end\n"
        )
        self.assertIn('file', kinds)

    def test_net_http_request_class_construction_classified_as_http(self):
        kinds = self._sideeffect_kinds(
            "def send_webhook(uri)\n"
            "  req = Net::HTTP::Post.new(uri)\n"
            "end\n"
        )
        self.assertIn('http', kinds)


class TestBack649PhpTaxonomy(unittest.TestCase):
    """BACK-649 (sideeffects-recall-oracle/php, seventh language): real
    corpus misses found on WordPress, both bare stdlib builtins previously
    absent from _TAXONOMY_BY_LANG['php']."""

    def _sideeffect_kinds(self, src):
        from reveal.adapters.ast.nav_effects import collect_effects
        _, root, get_text, _ = _parse_php(src)
        effects = collect_effects(root, 1, 999, get_text, language='php')
        return {e['kind'] for e in effects}

    def test_error_reporting_classified_as_log(self):
        kinds = self._sideeffect_kinds(
            "<?php\n"
            "function wp_debug_mode() {\n"
            "    error_reporting( E_ALL );\n"
            "}\n"
        )
        self.assertIn('log', kinds)

    def test_fsockopen_classified_as_http(self):
        kinds = self._sideeffect_kinds(
            "<?php\n"
            "function connect($server, $port) {\n"
            "    $fp = fsockopen($server, $port, $errno, $errstr);\n"
            "}\n"
        )
        self.assertIn('http', kinds)


class TestBack547CSharpTaxonomy(unittest.TestCase):
    """BACK-547 (sideeffects-recall-oracle/csharp, eighth language, Jellyfin
    corpus): two real corpus misses, both bare stdlib idioms previously
    absent from _TAXONOMY_BY_LANG['csharp']. The tokenizer doesn't split
    camelCase, so an async/read-side sibling of an already-listed pattern
    needs its own explicit entry."""

    def test_savechangesasync_classifies_as_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('dbContext.SaveChangesAsync'), 'db')

    def test_streamreader_classifies_as_file(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new StreamReader'), 'file')


class TestBack547RustDbEnvTaxonomy(unittest.TestCase):
    """heed (LMDB binding) transaction acquisition (`.read_txn()`/
    `.write_txn()`) and bare `env::var` (after `use std::env;`) were both
    unclassified -- neither carries the `std::`/type-name prefix the prior
    rust taxonomy entries required. Deliberately no bare `.commit` entry:
    since per-language taxonomy tables are also merged into the fully
    unscoped `_COMPILED_ALL` table, a bare `.commit` pattern regressed the
    existing BACK-594 `conn`/`connection` precedent live in this loop's own
    test run (`classify_call('conn::commit')`, unscoped, started returning
    'db' again) -- `read_txn`/`write_txn` alone were sufficient for full
    corpus recall on this category."""

    def test_read_txn_write_txn_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('index::read_txn', language='rust'), 'db')
        self.assertEqual(classify_call('index::write_txn', language='rust'), 'db')

    def test_bare_commit_not_added_unscoped(self):
        # Regression guard for the BACK-594 conn/connection precedent this
        # loop nearly broke -- 'commit' must stay OUT of the rust taxonomy
        # as a bare unscoped-visible pattern.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('conn::commit'))

    def test_bare_env_var_classified_env(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('env::var', language='rust'), 'env')
        self.assertEqual(classify_call('env::var_os', language='rust'), 'env')

    def test_fully_qualified_std_env_still_classified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std::env::var', language='rust'), 'env')


class TestBack547KotlinSqlDelightTaxonomy(unittest.TestCase):
    """SQLDelight's query-execution/transaction idiom
    (`countQuery.executeAsOne()`, `.executeAsList()`, `.executeAsOneOrNull()`,
    `transacter.transactionWithResult(...)`) is a single camelCase token --
    same tokenizer gap as C#'s `SaveChangesAsync` (BACK-547 eighth loop).
    Corpus: 68 executeAs*() calls + 4 transactionWithResult() calls across 17
    files in Tivi's data/ module, 0 classified before this fix."""

    def test_execute_as_variants_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        for variant in ('executeAsOne', 'executeAsList', 'executeAsOneOrNull'):
            self.assertEqual(
                classify_call(f'countQuery.{variant}', language='kotlin'), 'db',
                msg=f'{variant} should classify as db',
            )

    def test_transaction_with_result_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('transacter.transactionWithResult', language='kotlin'), 'db',
        )

    def test_bare_execute_still_common_scoped(self):
        # Sanity: the pre-existing common '->execute' pattern is untouched.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('cursor->execute', language='kotlin'), 'db')


class TestBack727KotlinSixCategoryWidening(unittest.TestCase):
    """BACK-727: deepened Kotlin past its db-only sideeffects-recall-oracle
    sample (BACK-547 tenth loop) to the full six-category sweep, widening
    the corpus scope from samples/kotlin/data to the whole samples/kotlin
    tree (Tivi). Recall: 82.46% -> 92.86%. New taxonomy entries below; the
    remaining misses (bare `File(` constructor, bare `client.<verb>(`) were
    corpus-checked and deliberately DECLINED as catastrophically collision-
    prone (see KOTLIN.md)."""

    def test_http_client_construction_classified(self):
        # `HttpClientFactory.create(...)` (TiviTrakt.kt) and
        # `OkHttpClient.Builder()...build()` (SharedPlatformApplicationComponent.kt)
        # are both dotted, receiver-scoped patterns (not bare verbs) --
        # corpus-verified as this corpus's actual http-client-CONSTRUCTION
        # idiom, zero cross-language collision risk since both segments are
        # required together.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('HttpClientFactory.create', language='kotlin'), 'http',
        )
        self.assertEqual(
            classify_call('OkHttpClient.Builder', language='kotlin'), 'http',
        )

    def test_delay_classified_sleep(self):
        # Kotlin coroutines' `delay(...)` is this corpus's entire sleep
        # idiom (2/2 real occurrences) -- _TAXONOMY_COMMON's 'sleep'/
        # 'usleep' never match it (different verb).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('delay', language='kotlin'), 'sleep')

    def test_bare_file_constructor_and_client_verb_not_classified(self):
        # Both DECLINED: corpus-wide check_taxonomy_collisions-style grep
        # (samples/*, all 18 language corpora) found bare `File(` fires
        # 388 times in java, 130 in cpp, 132 in gdscript_pixelorama, 101+
        # in dart alone (same shape Dart's OWN loop already declined for
        # `File`/`Directory` -- BACK-547 sideeffects-recall-oracle/dart);
        # bare `client.get/post/put/delete/patch/request(` fires 336 times
        # in go, 614 in lua_awesome, 40 in rust, 37 in ruby, 25 in java --
        # both would be exposed cross-language in classify_call()'s unscoped
        # _COMPILED_ALL fallback. Neither pattern was added; both stay
        # correctly unclassified misses.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('File', language='kotlin'))
        self.assertIsNone(classify_call('client.get', language='kotlin'))

    def test_buildconfig_property_read_classified_env(self):
        # BACK-644-shaped property/subscript channel gap: Android/KMP's
        # generated `BuildConfig.X` (build-time constants incl. API keys)
        # is a bare property read, invisible to classify_call() the same
        # way JS's `process.env.X` was. End-to-end: a function whose ONLY
        # effect is a BuildConfig read produces zero *call* sites.
        from reveal.adapters.ast.nav_effects import collect_effects
        parser = ts.get_parser('kotlin')
        src = textwrap.dedent("""
        fun provideApiKey(): String = BuildConfig.TMDB_API_KEY
        """).lstrip('\n')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')

        effects = collect_effects(root, 1, 999, get_text, language='kotlin')
        self.assertEqual(
            [(e['line'], e['kind'], e['callee'], e['via']) for e in effects],
            [(1, 'env', 'BuildConfig.TMDB_API_KEY', 'property')],
        )

    def test_dao_value_hop_still_left_to_reveal_receiver_suffix(self):
        # Not a taxonomy change -- documents that reveal's PRE-EXISTING
        # `_classify_by_receiver_suffix` (BACK-547 tenth loop) already
        # handles the `Lazy<XxxDao>`-wrapped `watchedShowsDao.value.getX()`
        # DI idiom found in domain/src interactors, since it matches ANY
        # non-final segment ending in `dao` regardless of how many hops
        # follow. The oracle's OWN regex needed a matching `.value` hop
        # fix (build_oracle.py) to stop reporting this as a false-positive
        # miss -- see KOTLIN.md's oracle-bug section.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('watchedShowsDao.value.getUpNextShows'), 'db')


class TestBack547SwiftApolloHttpTaxonomy(unittest.TestCase):
    """Apollo GraphQL's `client.fetch(query:)` / `client.perform(mutation:)`
    (plus the completion-handler/async `fetchWithResult`/`performWithResult`
    overloads) is the dominant network idiom in Kickstarter's KsApi service
    layer (sideeffects-recall-oracle/swift, eleventh and final language): 100+
    call sites across Service.swift and its ApolloClient extensions, all
    unclassified before this fix. Scoped to `language='swift'` so it can never
    fire for Ruby's unrelated `reviewable.perform(...)` (Discourse action
    dispatch, 230 corpus hits in samples/ruby) or any other language's own
    'fetch'/'perform' verbs."""

    def test_bare_fetch_and_perform_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('apollo.fetch', language='swift'), 'http')
        self.assertEqual(classify_call('client.perform', language='swift'), 'http')

    def test_with_result_variants_classified_http(self):
        # Tokenizer doesn't split camelCase (same gap as C#'s SaveChangesAsync
        # / Kotlin's executeAsOne), so the WithResult compound needs its own entry.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('client.fetchWithResult', language='swift'), 'http')
        self.assertEqual(classify_call('client.performWithResult', language='swift'), 'http')

    def test_data_task_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('self.dataTask', language='swift'), 'http')

    def test_ruby_perform_not_classified_http(self):
        # Cross-language non-collision: Ruby's Reviewable#perform is an
        # unrelated business-logic action dispatcher (Discourse), not network.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('reviewable.perform', language='ruby'))


class TestBack725ZigTaxonomy(unittest.TestCase):
    """BACK-718/BACK-725 (Zig, fourteenth side-effect-recall language,
    corpus: TigerBeetle samples/zig/tigerbeetle/src). Zig had zero
    _TAXONOMY_BY_LANG entries before this loop; scoped to language='zig' so
    none of these can fire cross-language. All patterns corpus-grounded and
    corpus-collision-checked (scripts/check_taxonomy_collisions.py)."""

    def test_storage_sector_io_classified_file(self):
        # TigerBeetle's own storage abstraction (storage.zig): the ONLY
        # on-disk sector I/O call sites in the whole corpus.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(
            classify_call('grid.superblock.storage.read_sectors', language='zig'), 'file')
        self.assertEqual(
            classify_call('client_replies.storage.write_sectors', language='zig'), 'file')

    def test_io_wrapper_scoped_file_and_http(self):
        # Two-segment `io.<verb>` scoping (same technique as Lua's io.write/
        # io.read file entry) -- NOT a bare 'read'/'write'/'connect'/'send'
        # verb, which would be the C/Lua loops' declined catastrophic-
        # collision class.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('bus.io.connect', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.accept', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.listen', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.recv', language='zig'), 'http')
        self.assertEqual(classify_call('bus.io.send', language='zig'), 'http')
        self.assertEqual(classify_call('storage.io.write', language='zig'), 'file')
        self.assertEqual(classify_call('storage.io.read', language='zig'), 'file')

    def test_zig_stdlib_file_camelcase_compounds(self):
        # Tokenizer doesn't split camelCase (same gap class as C#'s
        # SaveChangesAsync / Kotlin's executeAsOne / Swift's
        # fetchWithResult): std.fs's own compound method names are each a
        # single opaque token, distinct from any bare COMMON verb.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('project_root.openDir', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().openFile', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().makeOpenPath', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().deleteTree', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.selfExePath', language='zig'), 'file')
        self.assertEqual(classify_call('std.fs.cwd().statFile', language='zig'), 'file')
        self.assertEqual(classify_call('shell.cwd.realpathAlloc', language='zig'), 'file')
        self.assertEqual(classify_call('testing.copyFileAbsolute', language='zig'), 'file')

    def test_posix_syscalls_classified_file_and_http(self):
        # Bare POSIX syscall names -- corpus-collision-checked (universally
        # file-I/O-only across every corpus language, unlike a generic verb
        # like 'read'/'write' alone).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('posix.pwrite', language='zig'), 'file')
        self.assertEqual(classify_call('posix.fsync', language='zig'), 'file')
        # Two-segment 'posix.<verb>' (matches both the fully-qualified
        # std.posix.X form and a local `const posix = std.posix;` alias) --
        # NOT the declined bare 'connect'/'socket'/'accept' alone.
        self.assertEqual(classify_call('std.posix.connect', language='zig'), 'http')
        self.assertEqual(classify_call('posix.connect', language='zig'), 'http')
        self.assertEqual(classify_call('posix.socket', language='zig'), 'http')
        # Trailing-delimiter prefix convention (same shape as Lua's
        # ngx.socket. entry): matches any std.net.* call regardless of verb.
        self.assertEqual(classify_call('std.net.tcpConnectToAddress', language='zig'), 'http')

    def test_env_camelcase_compounds(self):
        # std.process.getEnvVarOwned/getEnvMap -- distinct camelCase tokens
        # from COMMON's pre-existing bare 'getenv' (which already covers the
        # older/simpler std.posix.getenv form, unaffected by this addition).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std.process.getEnvVarOwned', language='zig'), 'env')
        self.assertEqual(classify_call('std.process.getEnvMap', language='zig'), 'env')
        self.assertEqual(classify_call('std.posix.getenv', language='zig'), 'env')

    def test_debug_print_classified_log_not_bare_print(self):
        # std.debug.print -- Zig's raw stdout debug-print primitive used
        # corpus-wide for benchmark/test-harness output. Scoped two-segment
        # 'debug.print', NOT bare 'print' (the same catastrophic-collision
        # class as Python's print()/JS's console.log, declined everywhere
        # this program has touched a receiverless print idiom).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('std.debug.print', language='zig'), 'log')
        self.assertIsNone(classify_call('print', language='zig'))

    def test_zig_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop zig had no _TAXONOMY_BY_LANG entry
        # at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's fix).
        # A Python/PHP-only builtin must still never leak into a Zig file.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='zig'))


class TestBack720ScalaTaxonomy(unittest.TestCase):
    """BACK-718/BACK-720 (Scala, fifteenth side-effect-recall language,
    corpus: GitBucket samples/scala/src/main -- a real production
    Scala/Scalatra Git-hosting web app, NOT sbt itself despite the task's
    initial description; see scala/SCALA.md). Scala had zero
    _TAXONOMY_BY_LANG entries before this loop; scoped to language='scala'
    so none of these can fire cross-language. All patterns corpus-grounded
    and corpus-collision-checked (scripts/check_taxonomy_collisions.py)."""

    def test_slick_terminal_methods_classified_db(self):
        # Slick's blocking-API TERMINAL methods -- distinctive camelCase/
        # dotted compounds, NOT the bare filter/insert/update/delete/list/
        # first/result verbs Slick chains them onto (declined -- see
        # test_slick_bare_verbs_deliberately_unclassified below).
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('Priorities.filter(x).firstOption', language='scala'), 'db')
        self.assertEqual(classify_call('withSession', language='scala'), 'db')
        self.assertEqual(classify_call('Database.forDataSource', language='scala'), 'db')
        self.assertEqual(classify_call('Database.forURL', language='scala'), 'db')

    def test_slick_bare_verbs_deliberately_unclassified(self):
        # GitBucket's Slick DAO layer is syntactically indistinguishable
        # from Scala's own built-in collection/Option methods
        # (List.filter/Option.filter, etc) -- classify_call only sees
        # callee text, never a receiver's static type, so there is no way
        # to scope 'filter'/'insert'/'update'/'delete' narrower than "the
        # whole call" without the exact catastrophic cross-language
        # collision this program has repeatedly declined (Lua's
        # BACK-636/633 class). Locks in the DECISION, not a gap to fix.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('Priorities.filter', language='scala'))
        self.assertIsNone(classify_call('query.insert', language='scala'))
        self.assertIsNone(classify_call('query.update', language='scala'))
        self.assertIsNone(classify_call('query.delete', language='scala'))

    def test_java_io_constructor_calls_classified_file(self):
        # `new File(...)`/`new FileOutputStream(...)`/etc -- only visible
        # at all after this loop's `instance_expression` CALL_NODE_TYPES fix
        # (Scala's grammar node for `new Foo(args)`, distinct from PHP/C#'s
        # `object_creation_expression`); see
        # TestScalaInstanceExpressionCalls below for the structural half of
        # this fix. Emits "new <Name>" via _extract_scala_instance_callee,
        # the same convention _extract_object_creation_callee established
        # for PHP's 'new pdo'.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('new File', language='scala'), 'file')
        self.assertEqual(classify_call('new FileOutputStream', language='scala'), 'file')
        self.assertEqual(classify_call('new FileInputStream', language='scala'), 'file')
        self.assertEqual(classify_call('new FileWriter', language='scala'), 'file')
        self.assertEqual(classify_call('new HttpPost', language='scala'), 'http')
        self.assertEqual(classify_call('new HttpGet', language='scala'), 'http')

    def test_apache_commons_fileutils_classified_file(self):
        # Bare 'fileutils' receiver -- distinctive compound noun, matches
        # any FileUtils.* call regardless of trailing verb (same
        # "namespaced receiver, no bare verb" shape as Zig's std.net./Lua's
        # ngx.socket. prefix entries). Corpus-collision-checked: Java/Ruby
        # hits are the SAME Apache Commons IO / Ruby stdlib FileUtils
        # module, a corroborating idiom, not a collision.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('FileUtils.deleteDirectory', language='scala'), 'file')
        self.assertEqual(classify_call('FileUtils.copyFile', language='scala'), 'file')
        self.assertEqual(classify_call('f.mkdirs', language='scala'), 'file')
        self.assertEqual(classify_call('f.createNewFile', language='scala'), 'file')

    def test_httpclientbuilder_classified_http(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('HttpClientBuilder.create', language='scala'), 'http')

    def test_java_interop_env_needs_own_scala_entry(self):
        # Java-interop finding: Java's OWN _TAXONOMY_BY_LANG['java'] entry
        # for System.getProperty (BACK-639) does NOT extend to Scala files
        # even though both compile to the identical java.lang.System class
        # -- classify_call() only merges COMMON + the file's OWN language
        # bucket, with no cross-JVM-language sharing mechanism. Duplicated
        # here rather than shared.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('System.getProperty', language='scala'), 'env')
        self.assertIsNone(classify_call('System.getProperty', language='rust'))

    def test_scala_unmapped_before_this_loop_now_scoped(self):
        # Sanity-lock: before this loop scala had no _TAXONOMY_BY_LANG entry
        # at all, so it fell back to _COMPILED_COMMON_ONLY (BACK-722's fix),
        # confirmed for a 4th language. A Python/PHP-only builtin, and the
        # ubiquitous collection-method bare verbs above, must never leak.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('session_start', language='scala'))


