#!/bin/bash
# MySQL Test Container Setup for Reveal mysql:// adapter testing
# Tests multiple MySQL versions and connection schemes

set -e

echo "🚀 Setting up MySQL test containers for Reveal adapter testing"
echo "================================================================"

# Cleanup any existing test containers
echo "🧹 Cleaning up existing test containers..."
podman rm -f mysql57-test mysql80-test mysql84-test 2>/dev/null || true

# MySQL 5.7 - Legacy version
echo ""
echo "📦 Starting MySQL 5.7 (port 3357)..."
podman run -d \
  --name mysql57-test \
  -e MYSQL_ROOT_PASSWORD=testpass57 \
  -e MYSQL_DATABASE=testdb \
  -e MYSQL_USER=testuser \
  -e MYSQL_PASSWORD=testpass \
  -p 3357:3306 \
  docker.io/library/mysql:5.7 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# MySQL 8.0 - Current stable
echo "📦 Starting MySQL 8.0 (port 3380)..."
podman run -d \
  --name mysql80-test \
  -e MYSQL_ROOT_PASSWORD=testpass80 \
  -e MYSQL_DATABASE=testdb \
  -e MYSQL_USER=testuser \
  -e MYSQL_PASSWORD=testpass \
  -p 3380:3306 \
  docker.io/library/mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# MySQL 8.4 - Latest LTS
echo "📦 Starting MySQL 8.4 (port 3384)..."
podman run -d \
  --name mysql84-test \
  -e MYSQL_ROOT_PASSWORD=testpass84 \
  -e MYSQL_DATABASE=testdb \
  -e MYSQL_USER=testuser \
  -e MYSQL_PASSWORD=testpass \
  -p 3384:3306 \
  docker.io/library/mysql:8.4 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

echo ""
echo "⏳ Waiting for MySQL containers to be ready..."
sleep 15

# Test connections
echo ""
echo "🔍 Testing connections..."

for port in 3357 3380 3384; do
  version=$(echo $port | sed 's/33//')
  echo -n "  MySQL $version (port $port): "
  if podman exec mysql${version}-test mysqladmin ping -h localhost -u root -ptestpass${version} --silent 2>/dev/null; then
    echo "✅ Ready"
  else
    echo "⚠️  Not ready yet (may need more time)"
  fi
done

echo ""
echo "✅ MySQL test containers started!"
echo ""
echo "📋 Connection Details:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MySQL 5.7:"
echo "  Host: localhost:3357"
echo "  Root: root / testpass57"
echo "  User: testuser / testpass"
echo "  URI:  mysql://root:testpass57@localhost:3357"
echo ""
echo "MySQL 8.0:"
echo "  Host: localhost:3380"
echo "  Root: root / testpass80"
echo "  User: testuser / testpass"
echo "  URI:  mysql://root:testpass80@localhost:3380"
echo ""
echo "MySQL 8.4:"
echo "  Host: localhost:3384"
echo "  Root: root / testpass84"
echo "  User: testuser / testpass"
echo "  URI:  mysql://root:testpass84@localhost:3384"
echo ""
echo "📝 Test with Reveal:"
echo "  reveal mysql://root:testpass80@localhost:3380"
echo "  reveal mysql://root:testpass80@localhost:3380/connections"
echo "  reveal mysql://root:testpass80@localhost:3380/innodb"
echo ""
echo "🧪 Test with env vars:"
echo "  export MYSQL_HOST=localhost"
echo "  export MYSQL_PORT=3380"
echo "  export MYSQL_USER=root"
echo "  export MYSQL_PASSWORD=testpass80"
echo "  reveal mysql://"
echo ""
echo "🗑️  Cleanup: podman rm -f mysql57-test mysql80-test mysql84-test"
