"""Tests for HCL/Terraform analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.hcl import HCLAnalyzer


class TestHCLAnalyzer(unittest.TestCase):
    """Test suite for HCL/Terraform file analysis."""

    def test_basic_terraform_resource(self):
        """Should parse basic Terraform resource block."""
        code = '''
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"

  tags = {
    Name = "HelloWorld"
    Environment = "Dev"
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return valid structure (dict)
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_variables(self):
        """Should parse Terraform variable definitions."""
        code = '''
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "instance_count" {
  description = "Number of instances"
  type        = number
  default     = 1
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_outputs(self):
        """Should parse Terraform output definitions."""
        code = '''
output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.web.id
}

output "instance_public_ip" {
  description = "Public IP address of the EC2 instance"
  value       = aws_instance.web.public_ip
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_module(self):
        """Should parse Terraform module blocks."""
        code = '''
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  version = "3.0.0"

  name = "my-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["us-west-2a", "us-west-2b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  enable_vpn_gateway = false

  tags = {
    Terraform   = "true"
    Environment = "prod"
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_data_source(self):
        """Should parse Terraform data source blocks."""
        code = '''
data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_locals(self):
        """Should parse Terraform locals block."""
        code = '''
locals {
  common_tags = {
    Project     = "MyProject"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  instance_name = "${var.project}-${var.environment}-instance"

  az_count = length(data.aws_availability_zones.available.names)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_terraform_provider(self):
        """Should parse Terraform provider configuration."""
        code = '''
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    bucket = "my-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-west-2"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_tfvars_file(self):
        """Should parse Terraform variable values file (.tfvars)."""
        code = '''
region = "us-east-1"
instance_type = "t2.medium"
instance_count = 3

tags = {
  Environment = "Production"
  Owner       = "DevOps Team"
}

cidr_blocks = [
  "10.0.0.0/16",
  "10.1.0.0/16"
]
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tfvars', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generic_hcl_file(self):
        """Should parse generic HCL configuration file."""
        code = '''
service {
  name = "web"
  port = 80

  check {
    interval = "10s"
    timeout  = "2s"
  }
}

app "frontend" {
  config = {
    port = 3000
    host = "localhost"
  }

  build {
    use "docker" {
      dockerfile = "./Dockerfile"
    }
  }

  deploy {
    use "kubernetes" {
      namespace = "production"
    }
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.hcl', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_complex_expressions(self):
        """Should handle complex HCL expressions and functions."""
        code = '''
resource "aws_security_group" "allow_web" {
  name        = "allow_web"
  description = "Allow web inbound traffic"
  vpc_id      = aws_vpc.main.id

  dynamic "ingress" {
    for_each = var.ingress_ports
    content {
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "allow-web-${var.environment}"
    }
  )
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in HCL files."""
        code = '''
variable "description" {
  description = "Application description with Unicode: 🚀 Terraform 世界 ¡Hola!"
  type        = string
  default     = "My awesome app 👍"
}

locals {
  greetings = {
    spanish = "¡Hola, mundo!"
    chinese = "你好，世界"
    russian = "Привет мир"
    emoji   = "🌍 🌎 🌏"
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tf', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = HCLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
