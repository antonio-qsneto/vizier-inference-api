locals {
  origin_id = "${var.name}-origin"
  # AWS managed CloudFront cache policy: Managed-CachingDisabled
  caching_disabled_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  use_custom_certificate     = trimspace(var.acm_certificate_arn) != ""
}

resource "aws_cloudfront_origin_request_policy" "all_viewer" {
  name    = "${var.name}-all-viewer"
  comment = "Forward all viewer headers/cookies/query strings for API traffic"

  cookies_config {
    cookie_behavior = "all"
  }

  headers_config {
    header_behavior = "allViewer"
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "HTTPS API edge for ${var.name}"
  price_class         = var.price_class
  wait_for_deployment = false
  aliases             = var.aliases

  origin {
    domain_name = var.origin_domain_name
    origin_id   = local.origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    allowed_methods = [
      "GET",
      "HEAD",
      "OPTIONS",
      "PUT",
      "PATCH",
      "POST",
      "DELETE",
    ]
    cached_methods = [
      "GET",
      "HEAD",
      "OPTIONS",
    ]

    cache_policy_id          = local.caching_disabled_policy_id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.all_viewer.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = local.use_custom_certificate ? false : true
    acm_certificate_arn            = local.use_custom_certificate ? trimspace(var.acm_certificate_arn) : null
    ssl_support_method             = local.use_custom_certificate ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  lifecycle {
    precondition {
      condition     = length(var.aliases) == 0 || local.use_custom_certificate
      error_message = "acm_certificate_arn is required when aliases are configured."
    }
  }

  tags = var.tags
}
