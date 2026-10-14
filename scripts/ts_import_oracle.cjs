// Independent source import oracle: TypeScript's parser and resolveModuleName.
// Reads the explicit tracked population from stdin; does not execute corpus code.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ts = require(process.env.REVEAL_TS_ORACLE_MODULE || './oracles/node_modules/typescript');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const config = input.config;
if (ts.version !== config.typescript_version || process.versions.node !== config.node_version) {
  throw new Error(`Oracle toolchain mismatch: TypeScript ${ts.version}, Node ${process.versions.node}`);
}
if (input.mode === 'jsx' || input.mode === 'interfaces') {
  const references = [], protocols = [];
  for (const file of input.importers) {
    const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
    if (source.parseDiagnostics.length) throw new Error(`TypeScript cannot parse ${file}`);
    ts.forEachChild(source, function visit(node) {
      const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const callee = node.tagName.getText(source).replace(/\s+/g, '');
        if (!callee.includes(':') && !(ts.isIdentifier(node.tagName) && ts.isIntrinsicJsxName(callee))) {
          references.push({ line, callee });
        }
      }
      if (ts.isInterfaceDeclaration(node)) protocols.push({ name: node.name.text, line });
      ts.forEachChild(node, visit);
    });
  }
  process.stdout.write(JSON.stringify({ references, protocols }));
  process.exit(0);
}
const root = path.resolve(input.root);
const scan = path.resolve(input.scan);
const relative = file => path.relative(root, file).split(path.sep).join('/');
const inside = file => { const rel = path.relative(scan, file); return rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel); };
const configReads = new Map();
const host = { ...ts.sys, readFile(file) {
  const text = ts.sys.readFile(file);
  if (text !== undefined) configReads.set(relative(path.resolve(file)), text);
  return text;
}};
let options;
if (config.tsconfig) {
  const filename = path.join(root, config.tsconfig);
  const loaded = ts.readConfigFile(filename, host.readFile);
  if (loaded.error) throw new Error(ts.flattenDiagnosticMessageText(loaded.error.messageText, '\n'));
  const parsed = ts.parseJsonConfigFileContent(loaded.config, host, path.dirname(filename));
  if (parsed.errors.length) {
    throw new Error(parsed.errors.map(e => ts.flattenDiagnosticMessageText(e.messageText, '\n')).join('\n'));
  }
  options = parsed.options;
} else {
  // JS source-only projects may have no compiler configuration; this explicit
  // resolution population is committed in the manifest, not inferred by Reveal.
  const parsed = ts.convertCompilerOptionsFromJson(config.compiler_options, root);
  if (parsed.errors.length) throw new Error('Invalid compiler_options for oracle');
  options = parsed.options;
}
const cache = ts.createModuleResolutionCache(scan, f => f, options);
const edges = new Map();
let files = 0, directives = 0, unresolved = 0, excluded = 0, declarations = 0;
const population = [];
for (const raw of input.importers) {
  const file = path.resolve(raw);
  if (/\.d\.[cm]?ts$/.test(file)) { declarations++; continue; }
  population.push(relative(file));
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  if (source.parseDiagnostics.length) throw new Error(`TypeScript cannot parse ${relative(file)}`);
  files++;
  const specifiers = [];
  ts.forEachChild(source, function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteralLike(node.moduleSpecifier)) {
      specifiers.push(node.moduleSpecifier.text);
    } else if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument) && ts.isStringLiteralLike(node.argument.literal)) {
      specifiers.push(node.argument.literal.text);
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference) && node.moduleReference.expression && ts.isStringLiteralLike(node.moduleReference.expression)) {
      specifiers.push(node.moduleReference.expression.text);
    } else if (ts.isCallExpression(node) && node.arguments.length && ts.isStringLiteralLike(node.arguments[0]) &&
               (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require'))) {
      specifiers.push(node.arguments[0].text);
    }
    ts.forEachChild(node, visit);
  });
  for (const specifier of specifiers) {
    directives++;
    const resolved = ts.resolveModuleName(specifier, file, options, ts.sys, cache).resolvedModule;
    if (!resolved) { unresolved++; continue; }
    const target = path.resolve(resolved.resolvedFileName);
    if (!inside(target) || target.split(path.sep).includes('node_modules') || /\.d\.[cm]?ts$/.test(target) ||
        !/\.[cm]?[jt]sx?$/.test(target) || target === file) { excluded++; continue; }
    const key = relative(target);
    if (!edges.has(key)) edges.set(key, new Set());
    edges.get(key).add(relative(file));
  }
}
const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const output = Object.fromEntries([...edges].sort(([a], [b]) => a.localeCompare(b)).map(([target, importers]) => [target, [...importers].sort()]));
process.stdout.write(JSON.stringify({ edges: output, coverage: {
  files, directives, unresolved_directives: unresolved, excluded_targets: excluded,
  declaration_files_skipped: declarations, population_digest: digest(population.sort()),
  config_digest: digest([...configReads].sort(([a], [b]) => a.localeCompare(b))),
  compiler_options_digest: digest(config.compiler_options || {}),
  typescript_version: ts.version, node_version: process.versions.node,
  scan_file_cap: config.scan_file_cap || 5000,
}}));
