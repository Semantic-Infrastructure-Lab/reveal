# Independent bounded relative-loader truth. Corpus sources are parsed, never run.
require 'ripper'
require 'json'
require 'pathname'
require 'digest'

class NativeParser < Ripper::SexpBuilderPP
  attr_reader :diagnostics

  def initialize(source, filename)
    super(source, filename)
    @diagnostics = []
  end

  def on_parse_error(message)
    @diagnostics << {line: lineno, column: column, message: message}
    super
  end
end

def identifier(node)
  return nil unless node.is_a?(Array)
  case node[0]
  when :fcall, :vcall, :command then node[1]
  when :call, :command_call then node[3]
  when :method_add_arg then identifier(node[1])
  end
end

def arguments(node)
  return nil unless node.is_a?(Array)
  node = node[1] if node[0] == :arg_paren
  return nil unless node.is_a?(Array) && node[0] == :args_add_block && node[2] == false
  node[1]
end

def plain_quoted_starts(source)
  Ripper.lex(source).each_cons(2).filter_map do |first, second|
    if first[1] == :on_tstring_beg && ["'", '"'].include?(first[2]) && second[1] == :on_tstring_content
      [second[0], true]
    end
  end.to_h
end

def path_literal(node, quoted_starts)
  return nil unless node.is_a?(Array) && node[0] == :string_literal
  content = node[1]
  return nil unless content.is_a?(Array) && content[0] == :string_content
  return nil unless content[1..].all? { |part| part.is_a?(Array) && part[0] == :@tstring_content }
  return nil unless content[1] && quoted_starts[content[1][2]]
  value = content[1..].map { |part| part[1] }.join
  value.match?(/\A[A-Za-z0-9_.\/-]+\z/) ? value : nil
end

def loader_site(token, args, receiver, contexts, quoted_starts)
  return nil unless token.is_a?(Array) && %w[require require_relative load].include?(token[1])
  list = arguments(args)
  literal = list&.length == 1 ? path_literal(list[0], quoted_starts) : nil
  named = contexts.reverse.find { |context| context.start_with?('def:', 'defs:') }
  uncertain = contexts.any? { |context| context.start_with?('block:', 'lambda') }
  scope = named ? 'local' : (uncertain ? nil : 'module')
  {line: token[2][0], column: token[2][1], operation: token[1], literal: literal,
   receiver: receiver, scope: scope, named_method: named, contexts: contexts,
   qualified_call: receiver == 'implicit' && !literal.nil? && !contexts.include?('attached_loader_block')}
end

def walk_sites(node, contexts, rows, quoted_starts)
  return unless node.is_a?(Array)
  case node[0]
  when :def
    node[2..].each { |child| walk_sites(child, contexts + ["def:#{node[1][1]}"], rows, quoted_starts) }
  when :defs
    node[4..].each { |child| walk_sites(child, contexts + ["defs:#{node[3][1]}"], rows, quoted_starts) }
  when :lambda
    node[1..].each { |child| walk_sites(child, contexts + ['lambda'], rows, quoted_starts) }
  when :method_add_block
    name = identifier(node[1])
    attached = name && %w[require require_relative load].include?(name[1])
    walk_sites(node[1], attached ? contexts + ['attached_loader_block'] : contexts, rows, quoted_starts)
    walk_sites(node[2], contexts + ["block:#{name ? name[1] : '?'}"], rows, quoted_starts)
  else
    site = case node[0]
           when :command then loader_site(node[1], node[2], 'implicit', contexts, quoted_starts)
           when :command_call then loader_site(node[3], node[4], 'explicit_receiver', contexts, quoted_starts)
           when :method_add_arg
             call = node[1]
             loader_site(identifier(call), node[2], call[0] == :fcall ? 'implicit' : 'explicit_receiver', contexts, quoted_starts)
           end
    rows << site if site
    node.each { |child| walk_sites(child, contexts, rows, quoted_starts) if child.is_a?(Array) }
  end
end

def parse_sites(file, source_name)
  source = File.binread(file)
  parser = NativeParser.new(source, source_name)
  tree = parser.parse
  if parser.error? || tree.nil?
    raise "parse failure in #{source_name}: #{JSON.generate(parser.diagnostics)}"
  end
  rows = []
  walk_sites(tree, [], rows, plain_quoted_starts(source))
  rows.each { |row| row[:source] = source_name }
  [rows, Digest::SHA256.hexdigest(source)]
end

def check_version(config)
  minimum = config['ruby_minimum_version']
  unless minimum.is_a?(String) && minimum.match?(/\A\d+\.\d+(?:\.\d+)?\z/)
    raise 'ruby_minimum_version must declare a native parser version'
  end
  numbers = ->(value) { (value.split('.').map(&:to_i) + [0, 0])[0, 3] }
  if (numbers.call(RUBY_VERSION) <=> numbers.call(minimum)) == -1
    raise "Ruby version mismatch: minimum #{minimum}, got #{RUBY_VERSION}"
  end
  if config['ruby_version'] && config['ruby_version'] != RUBY_VERSION
    raise "Ruby version mismatch: expected #{config['ruby_version']}, got #{RUBY_VERSION}"
  end
end

class RelativeOracle
  def initialize(input)
    check_version(input.fetch('config'))
    @root = File.realpath(input.fetch('root'))
    @scan = File.realpath(input.fetch('scan'))
    @targets = input.fetch('targets').to_h { |file| [File.expand_path(file), true] }
    @coverage = {files: 0, import_statements: 0, resolved_statements: 0,
                 outside_relative_subset: 0, unsupported_expressions: 0,
                 unresolved_targets: 0, scope_unknown_statements: 0, outside_scan: 0,
                 ruby_version: RUBY_VERSION, ruby_description: RUBY_DESCRIPTION,
                 ripper_version: Ripper::Version, oracle_digest: Digest::SHA256.file(__FILE__).hexdigest,
                 population: 'explicit-literal-relative-loader-sites', sites: [],
                 source_digests: {}, target_digests: {},
                 limitations: ['no corpus execution or runtime load-path/autoload inference',
                               'implicit single plain ASCII relative literals only',
                               'unknown lexical contexts use declared include/exclude fallback',
                               'opaque support for a qualified pair makes measurement unavailable',
                               'reflective dispatch and monkeypatched loader behavior unqualified',
                               'convention-contaminated pairs require separate graph qualification']}
  end

  def relative(path)
    value = Pathname.new(path).relative_path_from(Pathname.new(@root)).to_s
    File::ALT_SEPARATOR ? value.tr(File::ALT_SEPARATOR, '/') : value
  end

  def inside?(path, root)
    path.start_with?(root + File::SEPARATOR)
  end

  def resolve(file, literal)
    return nil unless literal
    path = File.expand_path(literal, File.dirname(file))
    path += '.rb' if File.extname(path).empty?
    return nil unless path.end_with?('.rb') && inside?(path, @root) && @targets[path]
    unless File.file?(path) && !File.symlink?(path) && File.realpath(path) == path
      raise "Target missing, linked or outside regular tracked population: #{relative(path)}"
    end
    path
  end

  def qualified_pairs(file, rows)
    pairs = Hash.new { |hash, key| hash[key] = [] }
    rows.each do |site|
      @coverage[:import_statements] += 1
      unless site[:operation] == 'require_relative'
        @coverage[:outside_relative_subset] += 1
        next
      end
      unless site[:qualified_call]
        @coverage[:unsupported_expressions] += 1
        next
      end
      target = resolve(file, site[:literal])
      unless target
        @coverage[:unresolved_targets] += 1
        next
      end
      unless inside?(target, @scan)
        @coverage[:outside_scan] += 1
        next
      end
      @coverage[:resolved_statements] += 1
      @coverage[:scope_unknown_statements] += 1 if site[:scope].nil?
      @coverage[:target_digests][relative(target)] = Digest::SHA256.file(target).hexdigest
      site[:target] = relative(target)
      pairs[target] << site[:scope]
    end
    pairs
  end

  def check_support(rows, pairs)
    return if pairs.empty?
    names = pairs.keys.map { |target| File.basename(target, '.rb') }
    rows.each do |site|
      next if site[:operation] == 'require_relative' && site[:qualified_call]
      literal = site[:literal]
      if literal.nil? || names.include?(File.basename(literal, '.rb'))
        raise "unqualified loader can affect relative pair in #{site[:source]}:#{site[:line]}"
      end
    end
  end

  def build(importers)
    all = Hash.new { |hash, key| hash[key] = {} }
    importers.each do |file|
      file = File.expand_path(file)
      unless inside?(file, @root) && File.file?(file) && !File.symlink?(file) && File.realpath(file) == file
        raise 'Importer missing, linked or outside corpus'
      end
      @coverage[:files] += 1
      rows, digest = parse_sites(file, relative(file))
      @coverage[:source_digests][relative(file)] = digest
      pairs = qualified_pairs(file, rows)
      check_support(rows, pairs)
      pairs.each { |target, scopes| all[relative(target)][relative(file)] = scopes }
      @coverage[:sites].concat(rows)
    end
    edges = {}
    lazy = {}
    all.sort.each do |target, importers_by_scope|
      edges[target] = importers_by_scope.keys.sort
      locals = importers_by_scope.select { |_importer, scopes| scopes.all? { |scope| scope == 'local' } }.keys.sort
      lazy[target] = locals unless locals.empty?
    end
    {edges: edges, lazy_only: lazy, coverage: @coverage}
  end
end

begin
  input = JSON.parse(STDIN.read)
  puts JSON.generate(RelativeOracle.new(input).build(input.fetch('importers')))
rescue StandardError => error
  warn "#{error.class}: #{error.message}"
  exit 1
end
