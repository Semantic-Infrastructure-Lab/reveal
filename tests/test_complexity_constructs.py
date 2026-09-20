"""Per-construct cyclomatic-complexity probes across languages (manual-testing sweep, 2026-09-19).

Each snippet has a hand-derived McCabe value: 1 + decision points, where `&&`/`||`/`??`/`?:`,
catch/except and case arms count, and `default`/plain `else` do not (the radon/lizard/Sonar
definition BACK-1081 adopted). Rows that disagree today are strict-xfail against the task that
owns the fix, so fixing one flips it to XPASS and forces the marker off.
"""
import pytest

from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

# (suffix, construct, source, expected, xfail task or None)
CASES = [
    ('py', 'if', 'def f(a):\n    if a:\n        return 1\n    return 2\n', 2, None),
    ('py', 'if/elif/else', 'def f(a):\n    if a == 1:\n        return 1\n    elif a == 2:\n        return 2\n    else:\n        return 3\n', 3, None),
    ('py', 'for', 'def f(a):\n    for x in a:\n        pass\n', 2, None),
    ('py', 'while', 'def f(a):\n    while a:\n        a -= 1\n', 2, None),
    ('py', 'ternary', 'def f(a):\n    return 1 if a else 2\n', 2, None),
    ('py', 'and/or', 'def f(a, b, c):\n    return a and b or c\n', 3, None),
    ('py', 'try/except x2', 'def f(a):\n    try:\n        a()\n    except ValueError:\n        pass\n    except KeyError:\n        pass\n', 3, None),
    ('py', 'listcomp+if', 'def f(a):\n    return [x for x in a if x]\n', 3, None),
    ('py', 'match', 'def f(a):\n    match a:\n        case 1:\n            return 1\n        case 2:\n            return 2\n        case _:\n            return 3\n', 4, None),
    ('py', 'with', 'def f(a):\n    with a:\n        pass\n', 1, None),
    ('js', 'if', 'function f(a){ if(a){return 1} return 2 }\n', 2, None),
    ('js', 'if/else if', 'function f(a){ if(a==1){return 1} else if(a==2){return 2} else {return 3} }\n', 3, None),
    ('js', 'for/while', 'function f(a){ for(let i=0;i<a;i++){} while(a){a--} }\n', 3, None),
    ('js', 'for-of', 'function f(a){ for(const x of a){} }\n', 2, None),
    ('js', 'ternary', 'function f(a){ return a ? 1 : 2 }\n', 2, None),
    ('js', '&& ||', 'function f(a,b,c){ return a && b || c }\n', 3, None),
    ('js', 'switch 2 cases+default', 'function f(a){ switch(a){ case 1: return 1; case 2: return 2; default: return 3 } }\n', 3, None),
    ('js', 'try/catch', 'function f(a){ try{a()}catch(e){} }\n', 2, None),
    ('js', '??', 'function f(a,b){ return a ?? b }\n', 2, None),
    ('go', 'if', 'package p\nfunc f(a int) int {\n\tif a > 0 {\n\t\treturn 1\n\t}\n\treturn 2\n}\n', 2, None),
    ('go', 'for', 'package p\nfunc f(a int) {\n\tfor i := 0; i < a; i++ {\n\t}\n}\n', 2, None),
    ('go', 'range', 'package p\nfunc f(a []int) {\n\tfor range a {\n\t}\n}\n', 2, None),
    ('go', '&& ||', 'package p\nfunc f(a, b, c bool) bool {\n\treturn a && b || c\n}\n', 3, None),
    ('go', 'switch 2+default', 'package p\nfunc f(a int) int {\n\tswitch a {\n\tcase 1:\n\t\treturn 1\n\tcase 2:\n\t\treturn 2\n\tdefault:\n\t\treturn 3\n\t}\n}\n', 3, None),
    ('java', 'if', 'class A { int f(int a){ if(a>0){return 1;} return 2; } }\n', 2, None),
    ('java', 'for/while', 'class A { void f(int a){ for(int i=0;i<a;i++){} while(a>0){a--;} } }\n', 3, None),
    ('java', 'foreach', 'class A { void f(int[] a){ for(int x: a){} } }\n', 2, None),
    ('java', 'ternary', 'class A { int f(int a){ return a>0 ? 1 : 2; } }\n', 2, None),
    ('java', '&& ||', 'class A { boolean f(boolean a, boolean b, boolean c){ return a && b || c; } }\n', 3, None),
    ('java', 'switch 2+default', 'class A { int f(int a){ switch(a){ case 1: return 1; case 2: return 2; default: return 3; } } }\n', 3, None),
    ('java', 'try/catch x2', 'class A { void f(){ try { g(); } catch(RuntimeException e) {} catch(Error e) {} } void g(){} }\n', 3, None),
    ('rb', 'if/elsif/else', 'def f(a)\n  if a == 1\n    1\n  elsif a == 2\n    2\n  else\n    3\n  end\nend\n', 3, None),
    ('rb', 'unless', 'def f(a)\n  unless a\n    1\n  end\nend\n', 2, None),
    ('rb', 'modifier if', 'def f(a)\n  return 1 if a\n  2\nend\n', 2, None),
    ('rb', 'while', 'def f(a)\n  while a\n    a -= 1\n  end\nend\n', 2, None),
    ('rb', 'ternary', 'def f(a)\n  a ? 1 : 2\nend\n', 2, None),
    ('rb', '&& ||', 'def f(a, b, c)\n  a && b || c\nend\n', 3, None),
    ('rb', 'case/when x2 else', 'def f(a)\n  case a\n  when 1 then 1\n  when 2 then 2\n  else 3\n  end\nend\n', 3, None),
    ('rb', 'rescue', 'def f(a)\n  a.call\nrescue StandardError\n  nil\nend\n', 2, None),
    ('php', 'if/elseif/else', '<?php\nfunction f($a){ if($a==1){return 1;} elseif($a==2){return 2;} else {return 3;} }\n', 3, None),
    ('php', 'foreach', '<?php\nfunction f($a){ foreach($a as $x){} }\n', 2, None),
    ('php', 'ternary', '<?php\nfunction f($a){ return $a ? 1 : 2; }\n', 2, None),
    ('php', '&& || and', '<?php\nfunction f($a,$b,$c){ return $a && $b || $c; }\n', 3, None),
    ('php', 'switch 2+default', '<?php\nfunction f($a){ switch($a){ case 1: return 1; case 2: return 2; default: return 3; } }\n', 3, None),
    ('php', 'catch', '<?php\nfunction f($a){ try { $a(); } catch (Exception $e) {} }\n', 2, None),
    ('php', '??', '<?php\nfunction f($a,$b){ return $a ?? $b; }\n', 2, None),
    ('rs', 'if/else if', 'fn f(a: i32) -> i32 { if a == 1 { 1 } else if a == 2 { 2 } else { 3 } }\n', 3, None),
    ('rs', 'for/while/loop', 'fn f(a: i32) { for _ in 0..a {} while a > 0 {} }\n', 3, None),
    ('rs', '&& ||', 'fn f(a: bool, b: bool, c: bool) -> bool { a && b || c }\n', 3, None),
    ('rs', 'match 3 arms', 'fn f(a: i32) -> i32 { match a { 1 => 1, 2 => 2, _ => 3 } }\n', 4, None),
    ('rs', 'if let', 'fn f(a: Option<i32>) -> i32 { if let Some(x) = a { x } else { 0 } }\n', 2, None),
    ('kt', 'if/else if', 'fun f(a: Int): Int { return if (a == 1) 1 else if (a == 2) 2 else 3 }\n', 3, None),
    ('kt', 'for/while', 'fun f(a: Int) { for (i in 0..a) {} while (a > 0) {} }\n', 3, None),
    ('kt', '&& ||', 'fun f(a: Boolean, b: Boolean, c: Boolean): Boolean { return a && b || c }\n', 3, None),
    ('kt', 'when 2+else', 'fun f(a: Int): Int { return when (a) { 1 -> 1; 2 -> 2; else -> 3 } }\n', 3, None),
    ('kt', 'try/catch', 'fun f(a: () -> Unit) { try { a() } catch (e: Exception) {} }\n', 2, None),
    ('kt', '?:', 'fun f(a: Int?): Int { return a ?: 0 }\n', 2, None),
    ('swift', 'if/else if', 'func f(_ a: Int) -> Int { if a == 1 { return 1 } else if a == 2 { return 2 } else { return 3 } }\n', 3, None),
    ('swift', 'for/while', 'func f(_ a: Int) { for _ in 0..<a {} while a > 0 {} }\n', 3, None),
    ('swift', '&& ||', 'func f(_ a: Bool, _ b: Bool, _ c: Bool) -> Bool { return a && b || c }\n', 3, None),
    ('swift', 'switch 2+default', 'func f(_ a: Int) -> Int { switch a { case 1: return 1; case 2: return 2; default: return 3 } }\n', 3, None),
    ('swift', 'guard', 'func f(_ a: Int?) -> Int { guard let x = a else { return 0 }; return x }\n', 2, None),
    ('swift', 'ternary', 'func f(_ a: Bool) -> Int { return a ? 1 : 2 }\n', 2, None),
    ('cs', 'if/else if', 'class A { int F(int a){ if(a==1){return 1;} else if(a==2){return 2;} else {return 3;} } }\n', 3, None),
    ('cs', 'for/foreach/while', 'class A { void F(int[] a){ for(int i=0;i<1;i++){} foreach(var x in a){} while(a.Length>0){} } }\n', 4, None),
    ('cs', 'ternary', 'class A { int F(bool a){ return a ? 1 : 2; } }\n', 2, None),
    ('cs', '&& ||', 'class A { bool F(bool a,bool b,bool c){ return a && b || c; } }\n', 3, None),
    ('cs', 'switch 2+default', 'class A { int F(int a){ switch(a){ case 1: return 1; case 2: return 2; default: return 3; } } }\n', 3, None),
    ('cs', 'catch', 'class A { void F(){ try { } catch(System.Exception e) { } } }\n', 2, None),
    ('cs', '??', 'class A { int F(int? a){ return a ?? 0; } }\n', 2, None),
    ('c', 'if/else if', 'int f(int a){ if(a==1){return 1;} else if(a==2){return 2;} else {return 3;} }\n', 3, None),
    ('c', 'for/while/do', 'void f(int a){ for(int i=0;i<a;i++){} while(a>0){a--;} do{a++;}while(a<3); }\n', 4, None),
    ('c', 'ternary', 'int f(int a){ return a ? 1 : 2; }\n', 2, None),
    ('c', '&& ||', 'int f(int a,int b,int c){ return a && b || c; }\n', 3, None),
    ('c', 'switch 2+default', 'int f(int a){ switch(a){ case 1: return 1; case 2: return 2; default: return 3; } }\n', 3, None),
    ('lua', 'if/elseif/else', 'local function f(a)\n  if a == 1 then return 1 elseif a == 2 then return 2 else return 3 end\nend\n', 3, None),
    ('lua', 'for/while/repeat', 'local function f(a)\n  for i=1,a do end\n  while a > 0 do a = a - 1 end\n  repeat a = a + 1 until a > 3\nend\n', 4, None),
    ('lua', 'and/or', 'local function f(a,b,c)\n  return a and b or c\nend\n', 3, None),
    ('dart', 'if/else if', 'int f(int a){ if(a==1){return 1;} else if(a==2){return 2;} else {return 3;} }\n', 3, None),
    ('dart', 'for/while', 'void f(int a){ for(var i=0;i<a;i++){} while(a>0){a--;} }\n', 3, None),
    ('dart', 'ternary', 'int f(bool a){ return a ? 1 : 2; }\n', 2, None),
    ('dart', '&& ||', 'bool f(bool a,bool b,bool c){ return a && b || c; }\n', 3, None),
    ('dart', 'switch 2+default', 'int f(int a){ switch(a){ case 1: return 1; case 2: return 2; default: return 3; } }\n', 3, None),
    ('dart', 'catch', 'void f(){ try { } catch(e) { } }\n', 2, None),
    ('dart', '??', 'int f(int? a){ return a ?? 0; }\n', 2, None),
    ('gd', 'if/elif/else', 'func f(a):\n\tif a == 1:\n\t\treturn 1\n\telif a == 2:\n\t\treturn 2\n\telse:\n\t\treturn 3\n', 3, None),
    ('gd', 'for/while', 'func f(a):\n\tfor x in a:\n\t\tpass\n\twhile a > 0:\n\t\ta -= 1\n', 3, None),
    ('gd', 'and/or', 'func f(a, b, c):\n\treturn a and b or c\n', 3, None),
    ('gd', 'ternary', 'func f(a):\n\treturn 1 if a else 2\n', 2, None),
    ('gd', 'match 2+default', 'func f(a):\n\tmatch a:\n\t\t1:\n\t\t\treturn 1\n\t\t2:\n\t\t\treturn 2\n\t\t_:\n\t\t\treturn 3\n', 4, None),
    ('scala', 'if/else if', 'object O { def f(a: Int): Int = if (a == 1) 1 else if (a == 2) 2 else 3 }\n', 3, None),
    ('scala', 'for/while', 'object O { def f(a: Int): Unit = { for (i <- 0 until a) {}; while (a > 0) {} } }\n', 3, None),
    # Scala infix operators are a bare `operator_identifier` shared with `+`; telling `&&`
    # apart needs source text the walkers do not have (BACK-1324).
    ('scala', '&& ||', 'object O { def f(a: Boolean, b: Boolean, c: Boolean): Boolean = a && b || c }\n', 3, 'BACK-1324'),
    ('scala', 'match 2+default', 'object O { def f(a: Int): Int = a match { case 1 => 1; case 2 => 2; case _ => 3 } }\n', 3, 'BACK-1318'),
    ('scala', 'try/catch', 'object O { def f(): Unit = try { g() } catch { case e: Exception => () }; def g(): Unit = {} }\n', 2, 'BACK-1318'),
    ('ts', 'if', 'function f(a: number): number { if (a) { return 1 } return 2 }\n', 2, None),
    ('ts', 'ternary', 'function f(a: boolean): number { return a ? 1 : 2 }\n', 2, None),
    ('ts', '&& ||', 'function f(a: boolean, b: boolean, c: boolean) { return a && b || c }\n', 3, None),
    ('ts', 'switch 2+default', 'function f(a: number) { switch(a){ case 1: return 1; case 2: return 2; default: return 3 } }\n', 3, None),
    # Operator tokens that must NOT count (BACK-1316 parent gate).
    ('cpp', 'rvalue-ref && is not a decision', 'void f(int&& x){ auto&& y = x; }\n', 1, None),
    ('js', '||= &&= ??= not counted', 'function f(a,b){ a ||= b; a &&= b; a ??= b }\n', 1, None),
    ('kt', '&& chain', 'fun f(a: Boolean, b: Boolean, c: Boolean): Boolean { return a && b && c }\n', 3, None),
    ('swift', '&& chain', 'func f(_ a: Bool, _ b: Bool, _ c: Bool) -> Bool { return a && b && c }\n', 3, None),
    ('rs', 'reference && is not a decision', 'fn f(a: &&i32) -> i32 { **a }\n', 1, None),
    ('zig', 'if/else if', 'fn f(a: bool) u8 { if (a) { return 1; } else if (!a) { return 2; } return 3; }\n', 3, None),
    ('zig', 'if expression', 'fn f(a: bool) u8 { const x = if (a) 1 else 2; return x; }\n', 2, None),
    ('zig', 'while', 'fn f(a: bool) void { while (a) { break; } }\n', 2, None),
    ('zig', 'for', 'fn f(a: []u8) void { for (a) |x| { _ = x; } }\n', 2, None),
    ('zig', 'and/or', 'fn f(a: bool, b: bool, c: bool) bool { return a and b or c; }\n', 3, None),
    ('zig', 'orelse', 'fn f(b: ?u8) u8 { return b orelse 2; }\n', 2, None),
    ('zig', 'catch', 'fn f(c: anyerror!u8) u8 { return c catch 3; }\n', 2, None),
    ('zig', 'switch 2+else', 'fn f(a: u8) u8 { switch (a) { 1 => return 1, 2 => return 2, else => return 3 } }\n', 3, None),
    # A nested fn (generic type constructor) has its own entry; its decisions must not also
    # inflate the enclosing function. funcs[0] is the outer `Wrap`.
    ('zig', 'nested fn not folded into outer', 'fn Wrap(comptime T: type) type {\n    return struct {\n        fn inner(a: bool) u8 { if (a) { return 1; } return 2; }\n    };\n}\n', 1, None),
]

def _param(row):
    ext, name, src, want, task = row
    marks = [pytest.mark.xfail(strict=True, reason=task)] if task else []
    return pytest.param(ext, src, want, id=f'{ext}-{name}', marks=marks)


@pytest.mark.parametrize('ext,src,want', [_param(r) for r in CASES])
def test_construct_complexity(tmp_path, ext, src, want):
    f = tmp_path / f't.{ext}'
    f.write_text(src.replace('{} while', '{}\n while').replace('{} foreach', '{}\n foreach').replace('{} do', '{}\n do'))
    funcs = get_analyzer(str(f))(str(f)).get_structure()['functions']
    assert funcs[0]['complexity'] == want
