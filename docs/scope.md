# Compatibility model

ContractLens compares **existing clients** against a candidate server contract.
It reads OpenAPI **3.0.x in JSON**, resolves local JSON Pointer references, and
checks operations, inherited parameters, JSON-schema-like request/response
properties, arrays, enums, types, nullability, required fields, content types,
response codes and authentication changes.

| Change | Request | Response |
| --- | --- | --- |
| Enum narrows | Breaking | Informational |
| Enum expands | Informational | Breaking |
| Becomes nullable | Informational | Breaking |
| Stops being nullable | Breaking | Informational |
| Adds required field | Breaking | Compatible guarantee |
| Drops required guarantee | Compatible relaxation | Breaking |

Type changes are conservatively breaking, even when a particular language
might accept them. Removed response properties are conservatively breaking
because existing clients may read optional fields. Removed request properties
and parameters need review because server behavior for unknown fields varies.

Constraints, schema composition, additionalProperties, formats and security
changes produce warnings rather than an invented compatibility guarantee.
Recursive object schemas are traversed once per schema pair. Direct cyclic
reference aliases and unresolved/external references are rejected.

## Boundaries

This is a focused initial release, **not a complete OpenAPI validator**. YAML,
OpenAPI 3.1, external references, callbacks, links, response headers, content
encoding, server URL changes and full JSON Schema subsumption are outside the
current rule set. Unchanged composition can still produce review warnings.
ReadOnly/writeOnly projection and discriminator semantics are not interpreted.
Schema fields outside the supported checks can change without a finding.

No findings means no change was detected by the supported rules; it is **not**
a proof that an API release is safe. Prefer `--fail-on warning` when using it as
a release gate, validate specifications independently, and retain integration
tests. Inputs are read locally. Reports contain no remote assets or telemetry.

## Exit codes

- `0`: selected failure policy passed.
- `1`: at least one finding matched the failure policy; output is still written.
- `2`: input, reference, or output error.

`--fail-on never` is useful for report generation and does not hide findings.
Output ordering is deterministic. No timestamps are injected into reports.
