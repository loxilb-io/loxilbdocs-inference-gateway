# AI Request Security Verification

The published workflow uses independently verified access and routing controls:

- [API-key management](../ai-gateway/api-key-management.md) for key-gated services;
- [data-plane JWT authentication](data-plane-jwt-auth.md) for supported JWT paths;
- [admission flow control](../ai-gateway/admission-flow-control.md) for configured
  request and capacity gates;
- [the Quickstart](../getting-started/quickstart.md) for positive delivery,
  rejected requests, independent backend receipts and scoped cleanup.

No PII-scanner or Llama Firewall deployment procedure or prevention guarantee
is published here. A configured access policy does not establish content
inspection, redaction or prompt-injection prevention.

Use synthetic, non-sensitive test inputs. Require independent backend evidence
for both allowed and rejected cases, and verify the specific protocol, identity
and rule used by the deployment.
