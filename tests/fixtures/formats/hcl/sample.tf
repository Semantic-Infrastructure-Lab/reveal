variable "region" {
  default = "us-east-1"
}

provider "aws" {
  region = var.region
}

resource "aws_instance" "web" {
  ami           = "ami-123"
  instance_type = "t3.micro"
}

module "vpc" {
  source = "./vpc"
}

output "ip" {
  value = aws_instance.web.public_ip
}

locals {
  env = "prod"
}
