# Changelog

All notable changes to the documentation site are recorded here. Versioned
snapshots of the site are published on `v*` tags via [mike](https://github.com/jimporter/mike);
this file explains what changed between them.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Admission Flow Control guide: the per-rule capacity admission gate
  (`fc_mode`, ceilings, bounded queue, adaptive ceiling, warm-up, tenant fair
  share, admission headers), its refusal codes, configuration examples for
  `curl` and `loxicmd`, metrics and troubleshooting. The `fc_*` fields,
  `loxicmd create lb --fc-*` flags, admission metrics, and maintenance drain
  behavior are reflected in the configuration reference, CLI reference,
  monitoring, troubleshooting, and readiness/maintenance pages.
- Open-source project scaffolding: governance, maintainers, contributing guide
  (with DCO and Conventional Commits policy), full Contributor Covenant v2.1
  code of conduct, security policy, issue/PR templates, Dependabot, CI
  (hygiene, strict build, link check, secret scan), and mike-versioned deploys.
- Documentation for the AI gateway feature set: model load balancing, LLM
  routing, KV-cache-aware routing, P/D disaggregation, vLLM/SGLang
  integration, SSE & quota management, API key management, MCP gateway, and
  the full configuration reference.
- Security guides (OPA L4 policy, mTLS for AI backends), operations guides
  (monitoring, Grafana, troubleshooting, audit logging), management-plane
  guides (LoxiLB UI, OAM API), and reference pages (API, CLI, system
  requirements).

### Changed

- Documentation hardening ahead of the public release: placeholder
  credentials in examples, production TLS-verification guidance, OPA server
  hardening notes, checksum guidance for third-party downloads, and corrected
  implementation-status notes verified against the gateway source.
