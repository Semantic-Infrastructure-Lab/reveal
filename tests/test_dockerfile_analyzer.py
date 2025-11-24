"""Tests for Dockerfile analyzer."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.dockerfile import DockerfileAnalyzer


class TestDockerfileAnalyzer(unittest.TestCase):
    """Test Dockerfile analyzer."""

    def create_temp_dockerfile(self, content: str) -> str:
        """Helper: Create temp Dockerfile."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "Dockerfile")
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_from_directive(self):
        """Test extraction of FROM directive."""
        content = """
FROM python:3.10-slim
FROM node:18 AS builder
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('from', structure)
            from_images = structure['from']
            self.assertEqual(len(from_images), 2)

            self.assertEqual(from_images[0]['name'], 'python:3.10-slim')
            self.assertEqual(from_images[1]['name'], 'node:18 AS builder')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_run_directives(self):
        """Test extraction of RUN directives."""
        content = """
FROM ubuntu:22.04
RUN apt-get update
RUN apt-get install -y curl wget
RUN echo "Setup complete"
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('run', structure)
            runs = structure['run']
            self.assertEqual(len(runs), 3)

            self.assertIn('apt-get update', runs[0]['content'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_copy_and_add(self):
        """Test extraction of COPY/ADD directives."""
        content = """
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
ADD app.tar.gz /app/
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('copy', structure)
            copies = structure['copy']
            self.assertEqual(len(copies), 2)

            self.assertIn('nginx.conf', copies[0]['content'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_env_directives(self):
        """Test extraction of ENV directives."""
        content = """
FROM python:3.10
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app
ENV DEBUG=false
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('env', structure)
            envs = structure['env']
            self.assertEqual(len(envs), 3)

            self.assertIn('PYTHONUNBUFFERED', envs[0]['content'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_expose_directive(self):
        """Test extraction of EXPOSE directives."""
        content = """
FROM nginx:alpine
EXPOSE 80
EXPOSE 443
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('expose', structure)
            exposes = structure['expose']
            self.assertEqual(len(exposes), 2)

            self.assertEqual(exposes[0]['content'], '80')
            self.assertEqual(exposes[1]['content'], '443')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_entrypoint_and_cmd(self):
        """Test extraction of ENTRYPOINT and CMD directives."""
        content = """
FROM python:3.10
ENTRYPOINT ["python", "app.py"]
CMD ["--host", "0.0.0.0"]
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('entrypoint', structure)
            self.assertIn('cmd', structure)

            self.assertEqual(len(structure['entrypoint']), 1)
            self.assertEqual(len(structure['cmd']), 1)

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_labels(self):
        """Test extraction of LABEL directives."""
        content = """
FROM alpine:latest
LABEL maintainer="test@example.com"
LABEL version="1.0"
LABEL description="Test container"
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('label', structure)
            labels = structure['label']
            self.assertEqual(len(labels), 3)

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_arg_directives(self):
        """Test extraction of ARG directives."""
        content = """
FROM python:3.10
ARG BUILD_DATE
ARG VERSION=1.0.0
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('arg', structure)
            args = structure['arg']
            self.assertEqual(len(args), 2)

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_workdir_directive(self):
        """Test extraction of WORKDIR directives."""
        content = """
FROM node:18
WORKDIR /app
WORKDIR /app/src
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('workdir', structure)
            workdirs = structure['workdir']
            self.assertEqual(len(workdirs), 2)
            self.assertEqual(workdirs[0]['content'], '/app')

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_line_continuation(self):
        """Test handling of line continuations with backslash."""
        content = """
FROM ubuntu:22.04
RUN apt-get update && \\
    apt-get install -y \\
        curl \\
        wget \\
        git
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('run', structure)
            runs = structure['run']
            self.assertEqual(len(runs), 1)

            # Should combine the continued lines
            self.assertIn('curl', runs[0]['content'])

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_comments_ignored(self):
        """Test that comments are properly ignored."""
        content = """
# This is a comment
FROM python:3.10
# Another comment
RUN echo "test"
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            # Should only find real directives, not comments
            self.assertEqual(len(structure['from']), 1)
            self.assertEqual(len(structure['run']), 1)

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_empty_dockerfile(self):
        """Test with empty Dockerfile."""
        content = ""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            # Should return empty structure
            self.assertEqual(structure, {})

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))

    def test_real_world_dockerfile(self):
        """Test with realistic multi-stage Dockerfile."""
        content = """
# Build stage
FROM node:18 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""
        path = self.create_temp_dockerfile(content)
        try:
            analyzer = DockerfileAnalyzer(path)
            structure = analyzer.get_structure()

            # Should find both FROM directives
            self.assertEqual(len(structure['from']), 2)

            # Should find multiple RUN, COPY, etc.
            self.assertGreater(len(structure['run']), 0)
            self.assertGreater(len(structure['copy']), 0)
            self.assertIn('expose', structure)
            self.assertIn('cmd', structure)

        finally:
            os.unlink(path)
            os.rmdir(os.path.dirname(path))


if __name__ == '__main__':
    unittest.main()
