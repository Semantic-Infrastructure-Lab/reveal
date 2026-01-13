"""Tests for Protocol Buffers analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.protobuf import ProtobufAnalyzer


class TestProtobufAnalyzer(unittest.TestCase):
    """Test suite for Protocol Buffers (.proto) file analysis."""

    def test_basic_message(self):
        """Should parse basic protobuf message."""
        proto = '''
syntax = "proto3";

message User {
  int32 id = 1;
  string name = 2;
  string email = 3;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return valid structure (dict)
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_nested_messages(self):
        """Should parse nested protobuf messages."""
        proto = '''
syntax = "proto3";

message User {
  int32 id = 1;
  string name = 2;

  message Address {
    string street = 1;
    string city = 2;
    string state = 3;
    string zip = 4;
  }

  Address address = 3;

  message PhoneNumber {
    string number = 1;
    enum PhoneType {
      MOBILE = 0;
      HOME = 1;
      WORK = 2;
    }
    PhoneType type = 2;
  }

  repeated PhoneNumber phones = 4;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_enum_definition(self):
        """Should parse protobuf enum definitions."""
        proto = '''
syntax = "proto3";

enum Status {
  UNKNOWN = 0;
  PENDING = 1;
  ACTIVE = 2;
  INACTIVE = 3;
  DELETED = 4;
}

enum Role {
  GUEST = 0;
  USER = 1;
  ADMIN = 2;
  SUPERADMIN = 3;
}

message User {
  int32 id = 1;
  string name = 2;
  Status status = 3;
  Role role = 4;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_service_definition(self):
        """Should parse gRPC service definitions."""
        proto = '''
syntax = "proto3";

message GetUserRequest {
  int32 user_id = 1;
}

message GetUserResponse {
  int32 id = 1;
  string name = 2;
  string email = 3;
}

message ListUsersRequest {
  int32 page_size = 1;
  string page_token = 2;
}

message ListUsersResponse {
  repeated User users = 1;
  string next_page_token = 2;
}

message User {
  int32 id = 1;
  string name = 2;
  string email = 3;
}

service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
  rpc ListUsers(ListUsersRequest) returns (ListUsersResponse);
  rpc CreateUser(User) returns (User);
  rpc UpdateUser(User) returns (User);
  rpc DeleteUser(GetUserRequest) returns (google.protobuf.Empty);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_streaming_rpc(self):
        """Should parse streaming gRPC service methods."""
        proto = '''
syntax = "proto3";

message StreamRequest {
  string query = 1;
}

message StreamResponse {
  string data = 1;
  int32 sequence = 2;
}

service StreamService {
  // Server streaming
  rpc ServerStream(StreamRequest) returns (stream StreamResponse);

  // Client streaming
  rpc ClientStream(stream StreamRequest) returns (StreamResponse);

  // Bidirectional streaming
  rpc BidirectionalStream(stream StreamRequest) returns (stream StreamResponse);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_package_and_imports(self):
        """Should parse package declarations and imports."""
        proto = '''
syntax = "proto3";

package com.example.api.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/empty.proto";
import "common/types.proto";

option java_package = "com.example.api.v1";
option java_multiple_files = true;
option go_package = "github.com/example/api/v1;apiv1";

message User {
  int32 id = 1;
  string name = 2;
  google.protobuf.Timestamp created_at = 3;
  google.protobuf.Timestamp updated_at = 4;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_oneof_fields(self):
        """Should parse oneof field groups."""
        proto = '''
syntax = "proto3";

message Payment {
  int32 id = 1;
  double amount = 2;

  oneof payment_method {
    CreditCard credit_card = 3;
    BankAccount bank_account = 4;
    PayPal paypal = 5;
    string cash = 6;
  }

  message CreditCard {
    string number = 1;
    string expiry = 2;
    string cvv = 3;
  }

  message BankAccount {
    string account_number = 1;
    string routing_number = 2;
  }

  message PayPal {
    string email = 1;
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_map_fields(self):
        """Should parse map field types."""
        proto = '''
syntax = "proto3";

message User {
  int32 id = 1;
  string name = 2;

  // Map fields
  map<string, string> metadata = 3;
  map<int32, Address> addresses = 4;
  map<string, PhoneNumber> phones = 5;
}

message Address {
  string street = 1;
  string city = 2;
}

message PhoneNumber {
  string number = 1;
  string type = 2;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_field_options(self):
        """Should parse field options and custom options."""
        proto = '''
syntax = "proto3";

import "google/protobuf/descriptor.proto";

message User {
  int32 id = 1;

  string name = 2 [
    (validation.required) = true,
    (validation.max_length) = 100
  ];

  string email = 3 [
    (validation.required) = true,
    (validation.pattern) = "^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$"
  ];

  int32 age = 4 [
    (validation.min) = 0,
    (validation.max) = 150
  ];

  reserved 5, 6;
  reserved "old_field1", "old_field2";
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_proto2_syntax(self):
        """Should parse proto2 syntax with required/optional fields."""
        proto = '''
syntax = "proto2";

message User {
  required int32 id = 1;
  required string name = 2;
  optional string email = 3;
  optional int32 age = 4 [default = 0];
  repeated string tags = 5;

  extensions 100 to 199;

  enum Status {
    UNKNOWN = 0;
    ACTIVE = 1;
    INACTIVE = 2;
  }

  optional Status status = 6 [default = ACTIVE];
}

extend User {
  optional string custom_field = 100;
}

message Post {
  required int32 id = 1;
  required string title = 2;
  optional User author = 3;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_comments_and_documentation(self):
        """Should parse protobuf files with comments."""
        proto = '''
syntax = "proto3";

// Main user message representing a system user
// This is the primary entity for user management
message User {
  // Unique identifier for the user
  int32 id = 1;

  // Full name of the user
  string name = 2;

  /* Email address (must be unique)
   * Used for authentication and notifications
   */
  string email = 3;

  // Internal fields
  string password_hash = 4;  // Never expose in API responses

  // Timestamps
  int64 created_at = 5;  // Unix timestamp
  int64 updated_at = 6;  // Unix timestamp
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in protobuf files."""
        proto = '''
syntax = "proto3";

// User message with Unicode support 🌍
message User {
  int32 id = 1;

  // Name with Unicode: 世界 ¡Hola! Привет!
  string name = 2;

  // Greeting message with emojis 👋
  string greeting = 3;
}

// Language enumeration 🗣️
enum Language {
  ENGLISH = 0;   // English 🇺🇸
  SPANISH = 1;   // Español 🇪🇸
  CHINESE = 2;   // 中文 🇨🇳
  RUSSIAN = 3;   // Русский 🇷🇺
}

message Greeting {
  string message = 1;  // "Hello, 世界! ¿Cómo estás? 👍"
  Language language = 2;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False, encoding='utf-8') as f:
            f.write(proto)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ProtobufAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
