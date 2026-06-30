variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type    = string
  default = "customer-request-agent"
}

# mock | anthropic | auto. Defaults to mock so a deploy works with no API key.
variable "agent_llm" {
  type    = string
  default = "mock"
}

variable "agent_model" {
  type    = string
  default = "claude-haiku-4-5"
}

variable "anthropic_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
