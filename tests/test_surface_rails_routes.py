"""BACK-1417: a Rails `routes.draw` block interpreted as the routing DSL.

`surface` read only `get '/path'` lines with a leading slash, so Discourse's
config/routes.rb gave 13 of its 1,120 routes: `get "a" => "c#a"`, `resources`,
`namespace`/`scope` prefixes and `member`/`collection` blocks were all
missed. The expected paths below are what ActionDispatch itself produces for
the same source (checked against a real Rails 7.1 RouteSet).
"""

import textwrap
from pathlib import Path

import pytest

from reveal.adapters.ast.nav_surface_rails import resolve_engine_mounts
from reveal.adapters.ast.nav_surface_ruby import scan_file_surface_ruby
from reveal.adapters.surface import _scan_surface

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


def _write(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding='utf-8')
    return str(path)


def _routes(tmp_path: Path, body: str):
    result = scan_file_surface_ruby(_write(tmp_path, 'config/routes.rb', body))
    return [(r['methods'], r['path']) for r in result['http']]


def _draw(body: str) -> str:
    return 'Rails.application.routes.draw do\n' + textwrap.indent(textwrap.dedent(body), '  ') + 'end\n'


def test_resources_expand_to_their_actions(tmp_path):
    routes = _routes(tmp_path, _draw('''
        resources :posts
        resources :tags, only: %i[index show]
        resources :users, except: [:new, :edit], path: "u", param: :username
    '''))
    assert sorted(routes) == sorted([
        ('GET', '/posts'), ('POST', '/posts'), ('GET', '/posts/new'),
        ('GET', '/posts/:id/edit'), ('GET', '/posts/:id'), ('PATCH|PUT', '/posts/:id'),
        ('DELETE', '/posts/:id'),
        ('GET', '/tags'), ('GET', '/tags/:id'),
        ('GET', '/u'), ('POST', '/u'), ('GET', '/u/:username'), ('PATCH|PUT', '/u/:username'),
        ('DELETE', '/u/:username'),
    ])


def test_singular_resource(tmp_path):
    routes = _routes(tmp_path, _draw('''
        resource :session, only: %i[show destroy] do
          get "passkey"
        end
    '''))
    assert sorted(routes) == [('DELETE', '/session'), ('GET', '/session'),
                              ('GET', '/session/passkey')]


def test_member_collection_nested_and_on(tmp_path):
    """Directly inside `resources` a route is nested (`:user_id`), as
    Mapper#decomposed_match does; member/collection/`on:` pick their scope."""
    routes = _routes(tmp_path, _draw('''
        resources :users, only: [] do
          member { put "suspend" }
          collection do
            get "list" => "users#index"
            get :search
          end
          get "badges"
          post "reset", on: :member
          resources :notes, only: [:index]
        end
    '''))
    assert routes == [
        ('PUT', '/users/:id/suspend'), ('GET', '/users/list'), ('GET', '/users/search'),
        ('GET', '/users/:user_id/badges'), ('POST', '/users/:id/reset'),
        ('GET', '/users/:user_id/notes'),
    ]


def test_canonical_symbol_action_is_the_scope_path(tmp_path):
    routes = _routes(tmp_path, _draw('''
        resources :photos, only: [] do
          member { get :show }
          collection { get :index }
        end
    '''))
    assert routes == [('GET', '/photos/:id'), ('GET', '/photos')]


def test_namespace_scope_and_targets(tmp_path):
    path = _write(tmp_path, 'config/routes.rb', _draw('''
        namespace :admin do
          get "" => "admin#index"
          resources :reports, only: [:show]
          namespace :api, path: "v1" do
            get "ping"
          end
        end
        scope path: nil, constraints: { format: :json } do
          get "health" => "health#show"
        end
        scope "/:locale" do
          get "about" => "pages#about"
        end
        scope module: "legacy" do
          resources :items, only: [:index]
        end
    '''))
    result = scan_file_surface_ruby(path)['http']
    assert [(r['methods'], r['path'], r['target']) for r in result] == [
        ('GET', '/admin', 'admin/admin#index'),
        ('GET', '/admin/reports/:id', 'admin/reports#show'),
        ('GET', '/admin/v1/ping', None),
        ('GET', '/health', 'health#show'),
        ('GET', '/:locale/about', 'pages#about'),
        ('GET', '/items', 'legacy/items#index'),
    ]


def test_match_root_mount_and_optional_segment(tmp_path):
    routes = _routes(tmp_path, _draw('''
        root to: "home#index"
        match "/404", to: "errors#show", via: %i[get post]
        match "/any", to: "x#y", via: :all
        mount Sidekiq::Web => "/sidekiq"
        mount Blog::Engine, at: "/blog"
        get "t/:id/bump/(:post_id)" => "t#bump"
    '''))
    assert routes == [
        ('GET', '/'), ('GET|POST', '/404'), ('ANY', '/any'), ('ANY', '/sidekiq'),
        ('ANY', '/blog'), ('GET', '/t/:id/bump(/:post_id)'),
    ]


def test_literal_loops_and_locals_are_unrolled_unknown_parts_stay_braced(tmp_path):
    routes = _routes(tmp_path, _draw('''
        base = "/c/:slug"
        get base => "c#show"
        %w[users u].each_with_index do |root_path, index|
          get "#{root_path}/#{base}/x" => "users#x"
        end
        Registry.filters.each do |filter|
          get "l/#{filter}" => "list##{filter}"
        end
    '''))
    assert routes == [('GET', '/c/:slug'), ('GET', '/users/c/:slug/x'), ('GET', '/u/c/:slug/x'),
                      ('GET', '/l/{filter}')]


def test_conditional_routes_carry_their_condition(tmp_path):
    path = _write(tmp_path, 'config/routes.rb', _draw('''
        get "/always" => "a#b"
        get "/test-only" => "a#b" if Rails.env.test?
        if Rails.env.development?
          mount Dev::Web => "/dev"
        else
          mount Prod::Web => "/prod"
        end
    '''))
    result = {r['path']: r.get('condition') for r in scan_file_surface_ruby(path)['http']}
    assert result == {'/always': None, '/test-only': 'if Rails.env.test?',
                      '/dev': 'if Rails.env.development?',
                      '/prod': 'unless Rails.env.development?'}


def test_draw_level_verb_override_disables_the_verb(tmp_path):
    """Discourse defines `def patch(*); end` in its draw block: Mapper#patch
    is gone, for explicit routes and for a resource's update alike."""
    routes = _routes(tmp_path, _draw('''
        def patch(*)
        end
        patch "/x" => "a#b"
        resources :posts, only: [:update]
    '''))
    assert routes == [('PUT', '/posts/:id')]


def test_verb_outside_a_draw_block_keeps_the_sinatra_rule(tmp_path):
    routes = _routes(tmp_path, '''
        get '/sinatra' do
          'ok'
        end
        value = get('some_key')
    ''')
    assert routes == [('GET', '/sinatra')]


def test_engine_routes_resolve_under_their_mount_across_files(tmp_path):
    _write(tmp_path, 'config/routes.rb', '''
        Discourse::Application.routes.append { mount ::Assign::Engine, at: "/assign" }
        Discourse::Application.routes.draw { mount Plugin::AdminEngine, at: "/admin/plugins/p" }
    ''')
    _write(tmp_path, 'plugins/assign/config/routes.rb', '''
        Assign::Engine.routes.draw do
          put "/claim/:topic_id" => "assign#claim"
          get "/" => "assign#index"
        end
    ''')
    _write(tmp_path, 'plugins/p/lib/engine.rb', '''
        module Plugin
          AdminEngine.routes.draw { get "/rules" => "rules#index" }
        end
    ''')
    _write(tmp_path, 'plugins/q/config/routes.rb', '''
        Unmounted::Engine.routes.draw { get "/x" => "x#y" }
    ''')
    http = _scan_surface(tmp_path)['surfaces']['http']
    assert sorted((r['methods'], r['path']) for r in http) == sorted([
        ('ANY', '/assign'), ('ANY', '/admin/plugins/p'),
        ('PUT', '/assign/claim/:topic_id'), ('GET', '/assign'),
        ('GET', '/admin/plugins/p/rules'),
        ('GET', '/{Unmounted::Engine}/x'),
    ])


def test_engine_mounted_twice_keeps_its_prefix():
    entries = [
        {'decorator': 'mount', 'target': 'E::Engine', 'path': '/a'},
        {'decorator': 'mount', 'target': 'E::Engine', 'path': '/b'},
        {'decorator': 'get', 'target': None, 'path': '/{E::Engine}/x'},
    ]
    resolve_engine_mounts(entries)
    assert entries[2]['path'] == '/{E::Engine}/x'
