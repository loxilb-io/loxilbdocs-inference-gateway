# Firewall Policy Verification

Use the [firewall API reference](../reference/api.md) for the selected source
contract. This page does not provide an OPA watcher deployment procedure.

Before a policy change, capture the relevant rules and identify the exact rule
keys owned by the change. Apply only reviewed rules through the authenticated
management endpoint. Test an allowed connection and a denied connection, and
use independent backend observations to distinguish rejection from delivery.

After the test, remove only the owned rules and compare the remaining material
configuration with the pre-change readback. Configuration acceptance alone is
not proof that the intended traffic policy took effect.
