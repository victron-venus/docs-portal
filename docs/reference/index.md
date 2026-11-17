# Reference

Durable contracts that more than one project depends on. These change rarely,
and consumers pin against them.

## Service contracts

| Contract | Canonical source |
| --- | --- |
| D-Bus service naming and value semantics | [venus-os-integration-patterns](https://github.com/victron-venus/venus-os-integration-patterns/blob/main/docs/README.md) |
| MQTT topic layout for bridges | [venus-os-integration-patterns](https://github.com/victron-venus/venus-os-integration-patterns/blob/main/docs/README.md) |
| Service packaging and `/data` layout | [dbus-service-template](https://github.com/victron-venus/dbus-service-template/blob/main/README.md) |

## CI and release standard

| Contract | Canonical source |
| --- | --- |
| Release workflow and required checks | [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/release-workflow.md) |
| Reusable workflows and pinning policy | [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/README.md) |
| Versioning policy | [venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/VERSIONING.md) |

## Kubernetes and observability

| Contract | Canonical source |
| --- | --- |
| Cluster bootstrap and self-healing | [k3s-self-healing-public](https://github.com/ha-homelab/k3s-self-healing/blob/main/docs/README.md) |
| MQTT observability and tracing | [mqtt-observability-opentelemetry](https://github.com/victron-venus/mqtt-observability-opentelemetry/blob/main/docs/README.md) |

!!! warning "One canonical copy"
    Each row above is the only maintained copy. Do not vendor these documents
    into another repository; link them instead. Where a repository must carry a
    copy, it opens with a provenance line naming the canonical source.
