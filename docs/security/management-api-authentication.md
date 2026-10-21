# Management API Authentication

Management credentials authorize configuration access. They are separate from
the inference API key or JWT supplied to a service VIP.

## Prerequisites

Use an authenticated TLS management endpoint qualified for the exact deployed
image. Obtain its hostname, port, trusted CA and management token from the
deployment owner. This guide covers client credential handling and access
checks; it does not provide native identity-provider setup or user lifecycle
procedures.

## Configure and verify the clients

Follow the [Quickstart readiness procedure](../getting-started/quickstart.md#2-check-readiness)
to create owner-only credential files and set the same scheme, host, port and
CA for REST and CLI. The CLI token file must be an absolute path.

The [authentication check](../getting-started/quickstart.md#3-verify-management-authentication)
requires an unauthenticated configuration read to return `401` and the
credentialed read to return `200`. Stop if both requests succeed or if the
credentialed request fails. These checks establish access to that endpoint;
they do not prove every role, provider or revocation path.

## Credential handling

Keep tokens in permission-restricted files. Pass the protected header file to
curl and the absolute token-file path to the CLI. Do not put token values in
command arguments, screenshots, public logs or source control. Remove only
the files created for the lab after the final readback and cleanup.

Use the deployment's qualified credential-rotation procedure. A client-side
logout response alone is not proof that a token can no longer authorize a
request; verify that outcome independently.

## See also

- [Quickstart](../getting-started/quickstart.md)
- [Data-plane JWT authentication](data-plane-jwt-auth.md)
- [API-key management](../ai-gateway/api-key-management.md)
