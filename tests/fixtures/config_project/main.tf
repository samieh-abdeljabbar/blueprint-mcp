resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
}

resource "aws_db_instance" "main" {
  engine         = "postgres"
  instance_class = "db.t3.micro"
}

module "vpc" {
  source = "./modules/vpc"
}

variable "region" {
  default = "us-east-1"
}

variable "environment" {
  default = "production"
}
