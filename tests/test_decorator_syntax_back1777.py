"""reveal.conventions decorator syntax: one parser for at-sign and bracket spellings (BACK-1777)."""

import pytest

from reveal.conventions import decorator_attributes, decorator_name, decorator_names


@pytest.mark.parametrize('text, attributes', [
    ('@property', ['property']),
    ('@lru_cache(maxsize=1)', ['lru_cache(maxsize=1)']),
    ("@app.route('/x', methods=['GET'])", ["app.route('/x', methods=['GET'])"]),
    ('@available(iOS 13, *)', ['available(iOS 13, *)']),
    ('@field:JsonProperty("x")', ['JsonProperty("x")']),
    ('[HttpGet]', ['HttpGet']),
    ('[HttpGet("{id}"), Authorize]', ['HttpGet("{id}")', 'Authorize']),
    ('[HttpPost, Authorize(Roles = "a, b")]', ['HttpPost', 'Authorize(Roles = "a, b")']),
    ('[Route("api/[controller]")]', ['Route("api/[controller]")']),
    ('[return: NotNull]', ['NotNull']),
    ('#[Route("/a"), Deprecated]', ['Route("/a")', 'Deprecated']),
    ('#[derive(Debug, Clone)]', ['derive(Debug, Clone)']),
    ('#[tokio::test(flavor = "multi_thread")]', ['tokio::test(flavor = "multi_thread")']),
    ('#![allow(dead_code)]', ['allow(dead_code)']),
    ('[]', []),
    ('', []),
])
def test_attributes(text, attributes):
    assert decorator_attributes(text) == attributes


@pytest.mark.parametrize('attribute, name', [
    ('property', 'property'),
    ("app.route('/x')", 'app.route'),
    ('System.Obsolete("x")', 'System.Obsolete'),
    ('\\Symfony\\Component\\Routing\\Attribute\\Route("/b")', 'Symfony.Component.Routing.Attribute.Route'),
    ('tokio::test(flavor = "x")', 'tokio.test'),
    ('derive(Debug, Clone)', 'derive'),
])
def test_name(attribute, name):
    assert decorator_name(attribute) == name


@pytest.mark.parametrize('text, names', [
    ('@property', ['property']),
    ("@app.route('/x')", ['route']),
    ('#[tokio::test]', ['test']),
    ('[HttpPost, Authorize(Roles = "a")]', ['HttpPost', 'Authorize']),
    ('#[\\Foo\\Route("/b"), Deprecated]', ['Route', 'Deprecated']),
])
def test_bare_names(text, names):
    assert decorator_names(text) == names
