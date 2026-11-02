<?php
/** Independent, bounded static include-site oracle. Never executes corpus PHP. */
declare(strict_types=1);

function significantTokens(string $source): array {
    $result = [];
    foreach (token_get_all($source, TOKEN_PARSE) as $token) {
        if (is_array($token)) {
            if (in_array($token[0], [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)) {
                continue;
            }
            $result[] = ['id' => $token[0], 'text' => $token[1]];
        } else {
            $result[] = ['id' => null, 'text' => $token];
        }
    }
    return $result;
}

function delimiters(array $tokens): array {
    $stack = [];
    $pairs = [];
    foreach ($tokens as $i => $token) {
        $text = $token['text'];
        if ($token['id'] === T_ATTRIBUTE) {
            $text = '[';
        } elseif (in_array($token['id'], [T_CURLY_OPEN, T_DOLLAR_OPEN_CURLY_BRACES], true)) {
            $text = '{';
        } elseif ($token['id'] !== null) {
            continue;
        }
        if (in_array($text, ['(', '[', '{'], true)) {
            $stack[] = $i;
        } elseif (in_array($text, [')', ']', '}'], true)) {
            $open = array_pop($stack);
            if ($open === null) {
                throw new RuntimeException('Unbalanced native token delimiters');
            }
            $pairs[$open] = $i;
        }
    }
    if ($stack) {
        throw new RuntimeException('Unclosed native token delimiter');
    }
    return $pairs;
}

function functionRanges(array $tokens, array $pairs): array {
    $ranges = [];
    foreach ($tokens as $i => $token) {
        if (!in_array($token['id'], [T_FUNCTION, T_FN], true)) {
            continue;
        }
        $arrow = $token['id'] === T_FN;
        for ($j = $i + 1; $j < count($tokens); $j++) {
            if (isset($pairs[$j]) && $tokens[$j]['text'] !== '{') {
                $j = $pairs[$j];
            } elseif (!$arrow && $tokens[$j]['text'] === '{') {
                $ranges[] = [$j, $pairs[$j]];
                break;
            } elseif ($arrow && $tokens[$j]['id'] === T_DOUBLE_ARROW) {
                $start = ++$j;
                $ternaries = 0;
                while ($j < count($tokens)) {
                    if (isset($pairs[$j])) {
                        $j = $pairs[$j] + 1;
                    } elseif ($tokens[$j]['text'] === '?') {
                        $ternaries++;
                        $j++;
                    } elseif ($tokens[$j]['text'] === ':' && $ternaries > 0) {
                        $ternaries--;
                        $j++;
                    } elseif (in_array($tokens[$j]['text'], [';', ',', ')', ']', '}', ':'], true)) {
                        break;
                    } else {
                        $j++;
                    }
                }
                $ranges[] = [$start - 1, $j];
                break;
            } elseif ($tokens[$j]['text'] === ';') {
                break; // abstract/interface declaration has no function body
            }
        }
    }
    return $ranges;
}

function quotedLiteral(string $text): ?string {
    $body = substr($text, 1, -1);
    // Deliberately bounded: escaped filenames need separate expression qualification.
    return str_contains($body, '\\') ? null : $body;
}

function staticAtom(array $tokens, int &$at, string $directory, bool $dirnameAllowed): ?string {
    $token = $tokens[$at] ?? null;
    if ($token === null) {
        return null;
    }
    $at++;
    if ($token['id'] === T_DIR) {
        return $directory;
    }
    if ($token['id'] === T_CONSTANT_ENCAPSED_STRING) {
        return quotedLiteral($token['text']);
    }
    if ($token['text'] === '(') {
        $value = staticExpression($tokens, $at, $directory, $dirnameAllowed);
        if (($tokens[$at]['text'] ?? null) !== ')') {
            return null;
        }
        $at++;
        return $value;
    }
    if ($dirnameAllowed && $token['id'] === T_STRING && strtolower($token['text']) === 'dirname'
        && ($tokens[$at]['text'] ?? null) === '('
        && ($tokens[$at + 1]['id'] ?? null) === T_DIR
        && ($tokens[$at + 2]['text'] ?? null) === ')') {
        $at += 3;
        return dirname($directory);
    }
    return null;
}

function staticExpression(array $tokens, int &$at, string $directory, bool $dirnameAllowed): ?string {
    $value = staticAtom($tokens, $at, $directory, $dirnameAllowed);
    while ($value !== null && ($tokens[$at]['text'] ?? null) === '.') {
        $at++;
        $part = staticAtom($tokens, $at, $directory, $dirnameAllowed);
        if ($part === null) {
            return null;
        }
        $value .= $part;
    }
    return $value;
}

function relativePath(string $root, string $path): ?string {
    $prefix = rtrim($root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
    return str_starts_with($path, $prefix)
        ? str_replace(DIRECTORY_SEPARATOR, '/', substr($path, strlen($prefix))) : null;
}

function includeSites(string $file, array $config): array {
    $source = file_get_contents($file);
    if ($source === false) {
        throw new RuntimeException('Cannot read importer');
    }
    $tokens = significantTokens($source);
    $ranges = functionRanges($tokens, delimiters($tokens));
    // An unqualified namespaced dirname() can be overridden; never assume the builtin.
    $dirnameAllowed = !in_array(T_NAMESPACE, array_column($tokens, 'id'), true);
    foreach ($tokens as $i => $token) {
        if ($token['id'] === T_USE && ($tokens[$i + 1]['text'] ?? null) !== '(') {
            $dirnameAllowed = false; // namespace/trait imports are outside this expression subset
        }
    }
    $sites = [];
    foreach ($tokens as $i => $token) {
        if (!in_array($token['id'], [T_REQUIRE, T_REQUIRE_ONCE, T_INCLUDE, T_INCLUDE_ONCE], true)) {
            continue;
        }
        $at = $i + 1;
        $path = staticExpression($tokens, $at, dirname($file), $dirnameAllowed);
        // Full supported expression consumption, never accept a static prefix.
        if (!in_array($tokens[$at]['text'] ?? ';', [';', ',', ')', ']', '}', ':'], true)) {
            $path = null;
        }
        $absolute = $path !== null && (str_starts_with($path, DIRECTORY_SEPARATOR)
                    || preg_match('/^[a-zA-Z]:[\\\\\/]/', $path));
        if ($path !== null && !$absolute) {
            $path = ($config['literal_base'] ?? null) === 'importer'
                ? dirname($file) . DIRECTORY_SEPARATOR . $path : null;
        }
        $local = false;
        foreach ($ranges as [$start, $end]) {
            $local = $local || ($start < $i && $i < $end);
        }
        $sites[] = ['path' => $path, 'local' => $local];
    }
    return $sites;
}

function buildOracle(array $input): array {
    $root = realpath($input['root']);
    $config = $input['config'];
    if ($root === false) {
        throw new RuntimeException('Missing corpus root');
    }
    if (isset($config['php_version']) && $config['php_version'] !== PHP_VERSION) {
        throw new RuntimeException('PHP version mismatch: expected ' . $config['php_version'] . ', got ' . PHP_VERSION);
    }
    $pairs = [];
    $coverage = ['files' => 0, 'import_statements' => 0, 'resolved_statements' => 0,
                 'unsupported_expressions' => 0, 'unresolved_targets' => 0, 'php_version' => PHP_VERSION,
                 'population' => 'explicit-static-include-sites',
                 'limitations' => ['no runtime include_path/CWD/autoload', 'namespace use excluded',
                                   'lexical scope is not execution likelihood', 'bounded unescaped literal/dirname expressions',
                                   'unqualified dirname excluded in namespace/import contexts']];
    foreach ($input['importers'] as $file) {
        $file = realpath($file);
        $importer = $file === false ? null : relativePath($root, $file);
        if ($importer === null) {
            throw new RuntimeException('Importer missing or outside corpus');
        }
        $coverage['files']++;
        foreach (includeSites($file, $config) as $site) {
            $coverage['import_statements']++;
            if ($site['path'] === null) {
                $coverage['unsupported_expressions']++;
                continue;
            }
            $targetPath = realpath($site['path']);
            $target = $targetPath === false ? null : relativePath($root, $targetPath);
            if ($target === null || !is_file($targetPath)) {
                $coverage['unresolved_targets']++;
                continue;
            }
            $coverage['resolved_statements']++;
            $pairs[$target][$importer][] = $site['local'];
        }
    }
    $edges = [];
    $lazy = [];
    ksort($pairs);
    foreach ($pairs as $target => $importers) {
        ksort($importers);
        $edges[$target] = array_keys($importers);
        foreach ($importers as $importer => $localFlags) {
            if (!in_array(false, $localFlags, true)) {
                $lazy[$target][] = $importer;
            }
        }
    }
    return ['edges' => (object)$edges, 'lazy_only' => (object)$lazy, 'coverage' => $coverage];
}

try {
    $input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    echo json_encode(buildOracle($input), JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES), PHP_EOL;
} catch (Throwable $error) {
    fwrite(STDERR, get_class($error) . ': ' . $error->getMessage() . PHP_EOL);
    exit(1);
}
