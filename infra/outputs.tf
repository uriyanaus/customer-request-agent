output "api_endpoint" {
  description = "POST { \"request\": \"...\" } to this URL"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/decisions"
}
