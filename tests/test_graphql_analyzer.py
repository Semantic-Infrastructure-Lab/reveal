"""Tests for GraphQL analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.graphql import GraphQLAnalyzer


class TestGraphQLAnalyzer(unittest.TestCase):
    """Test suite for GraphQL schema and query file analysis."""

    def test_basic_type_definition(self):
        """Should parse basic GraphQL type definition."""
        schema = '''
type User {
  id: ID!
  name: String!
  email: String!
  age: Int
  posts: [Post!]!
}

type Post {
  id: ID!
  title: String!
  content: String
  author: User!
  createdAt: String!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return valid structure (dict)
            self.assertIsInstance(structure, dict)

            # Should extract types
            self.assertIn('types', structure)
            types = structure['types']
            self.assertEqual(len(types), 2)

            # Check User type
            user_type = next((t for t in types if t['name'] == 'User'), None)
            self.assertIsNotNone(user_type)
            self.assertIn('id', user_type['fields'])
            self.assertIn('name', user_type['fields'])
            self.assertIn('email', user_type['fields'])
            self.assertIn('posts', user_type['fields'])

            # Check Post type
            post_type = next((t for t in types if t['name'] == 'Post'), None)
            self.assertIsNotNone(post_type)
            self.assertIn('title', post_type['fields'])
            self.assertIn('author', post_type['fields'])

        finally:
            os.unlink(temp_path)

    def test_query_and_mutation_definitions(self):
        """Should parse Query and Mutation type definitions."""
        schema = '''
type Query {
  user(id: ID!): User
  users(limit: Int, offset: Int): [User!]!
  post(id: ID!): Post
  posts(authorId: ID): [Post!]!
}

type Mutation {
  createUser(name: String!, email: String!): User!
  updateUser(id: ID!, name: String, email: String): User
  deleteUser(id: ID!): Boolean!
  createPost(title: String!, content: String, authorId: ID!): Post!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

            # Should extract queries
            self.assertIn('queries', structure)
            queries = structure['queries']
            self.assertEqual(len(queries), 4)
            query_names = [q['name'] for q in queries]
            self.assertIn('user', query_names)
            self.assertIn('users', query_names)

            # Check query signatures include arguments and return types
            user_query = next((q for q in queries if q['name'] == 'user'), None)
            self.assertIsNotNone(user_query)
            self.assertIn('id: ID!', user_query['signature'])
            self.assertIn(': User', user_query['signature'])

            # Should extract mutations
            self.assertIn('mutations', structure)
            mutations = structure['mutations']
            self.assertEqual(len(mutations), 4)
            mutation_names = [m['name'] for m in mutations]
            self.assertIn('createUser', mutation_names)
            self.assertIn('deleteUser', mutation_names)

            # Check mutation signatures
            create_user = next((m for m in mutations if m['name'] == 'createUser'), None)
            self.assertIsNotNone(create_user)
            self.assertIn('name: String!', create_user['signature'])
            self.assertIn('email: String!', create_user['signature'])

        finally:
            os.unlink(temp_path)

    def test_interface_definition(self):
        """Should parse GraphQL interface definitions."""
        schema = '''
interface Node {
  id: ID!
}

interface Timestamped {
  createdAt: String!
  updatedAt: String!
}

type User implements Node & Timestamped {
  id: ID!
  name: String!
  email: String!
  createdAt: String!
  updatedAt: String!
}

type Post implements Node & Timestamped {
  id: ID!
  title: String!
  author: User!
  createdAt: String!
  updatedAt: String!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_enum_definition(self):
        """Should parse GraphQL enum definitions."""
        schema = '''
enum Role {
  ADMIN
  USER
  GUEST
}

enum PostStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type User {
  id: ID!
  name: String!
  role: Role!
}

type Post {
  id: ID!
  title: String!
  status: PostStatus!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

            # Should extract enums
            self.assertIn('enums', structure)
            enums = structure['enums']
            self.assertEqual(len(enums), 2)
            enum_names = [e['name'] for e in enums]
            self.assertIn('Role', enum_names)
            self.assertIn('PostStatus', enum_names)

            # Check enum values
            role_enum = next((e for e in enums if e['name'] == 'Role'), None)
            self.assertIsNotNone(role_enum)
            self.assertIn('values', role_enum)
            self.assertIn('ADMIN', role_enum['values'])
            self.assertIn('USER', role_enum['values'])

        finally:
            os.unlink(temp_path)

    def test_union_type(self):
        """Should parse GraphQL union types."""
        schema = '''
type Image {
  url: String!
  width: Int!
  height: Int!
}

type Video {
  url: String!
  duration: Int!
  thumbnail: String
}

type Audio {
  url: String!
  duration: Int!
  artist: String
}

union Media = Image | Video | Audio

type Post {
  id: ID!
  title: String!
  media: Media
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_input_type(self):
        """Should parse GraphQL input types."""
        schema = '''
input CreateUserInput {
  name: String!
  email: String!
  age: Int
  role: Role
}

input UpdateUserInput {
  name: String
  email: String
  age: Int
}

input PostFilter {
  authorId: ID
  status: PostStatus
  tags: [String!]
}

type Mutation {
  createUser(input: CreateUserInput!): User!
  updateUser(id: ID!, input: UpdateUserInput!): User
}

type Query {
  posts(filter: PostFilter): [Post!]!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_directives(self):
        """Should parse GraphQL directives."""
        schema = '''
directive @auth(requires: Role = USER) on OBJECT | FIELD_DEFINITION

directive @deprecated(
  reason: String = "No longer supported"
) on FIELD_DEFINITION | ENUM_VALUE

type User @auth(requires: ADMIN) {
  id: ID!
  name: String!
  email: String!
  password: String! @auth(requires: ADMIN)
  legacyField: String @deprecated(reason: "Use newField instead")
}

type Query {
  users: [User!]! @auth(requires: ADMIN)
  currentUser: User @auth(requires: USER)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_scalar_types(self):
        """Should parse custom scalar type definitions."""
        schema = '''
scalar DateTime
scalar Email
scalar URL
scalar JSON

type User {
  id: ID!
  name: String!
  email: Email!
  createdAt: DateTime!
  website: URL
  metadata: JSON
}

type Query {
  user(id: ID!): User
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_subscription_type(self):
        """Should parse Subscription type definitions."""
        schema = '''
type Subscription {
  userCreated: User!
  userUpdated(id: ID!): User!
  postPublished: Post!
  messageReceived(chatId: ID!): Message!
}

type Message {
  id: ID!
  content: String!
  author: User!
  timestamp: String!
}

type Query {
  messages(chatId: ID!): [Message!]!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_graphql_query_file(self):
        """Should parse GraphQL query file (.gql)."""
        query = '''
query GetUser($id: ID!) {
  user(id: $id) {
    id
    name
    email
    posts {
      id
      title
      createdAt
    }
  }
}

query GetUsers($limit: Int, $offset: Int) {
  users(limit: $limit, offset: $offset) {
    id
    name
    email
  }
}

mutation CreateUser($input: CreateUserInput!) {
  createUser(input: $input) {
    id
    name
    email
  }
}

fragment UserFields on User {
  id
  name
  email
  createdAt
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gql', delete=False, encoding='utf-8') as f:
            f.write(query)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_schema_with_comments(self):
        """Should parse schema with comments and descriptions."""
        schema = '''
"""
Main user type representing a registered user in the system.
"""
type User {
  "Unique identifier for the user"
  id: ID!

  "Full name of the user"
  name: String!

  "Email address (must be unique)"
  email: String!

  # Internal field - not exposed to clients
  passwordHash: String!

  "All posts created by this user"
  posts: [Post!]!
}

# Post represents a blog post or article
type Post {
  id: ID!
  title: String!
  content: String
  author: User!
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in GraphQL schemas."""
        schema = '''
type User {
  id: ID!
  """
  User name with Unicode support: 世界 🌍
  """
  name: String!

  "Greeting in multiple languages: ¡Hola! Привет! 你好!"
  greeting: String
}

enum Language {
  ENGLISH
  SPANISH  # Español 🇪🇸
  CHINESE  # 中文 🇨🇳
  RUSSIAN  # Русский 🇷🇺
}

type Query {
  "Get user with emoji support 👤"
  user(id: ID!): User
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphql', delete=False, encoding='utf-8') as f:
            f.write(schema)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GraphQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
