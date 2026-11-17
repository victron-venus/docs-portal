# Victron Venus documentation

Installation, integration and reference material for the Victron Venus OS
projects maintained by the [victron-venus](https://github.com/victron-venus)
organization.

<div class="grid cards" markdown>

- **Browse the projects**

    Every maintained project, grouped as in the public catalog, with each page
    generated from that repository's own documentation.

    [:octicons-arrow-right-24: Projects](projects/index.md)

- **Install and integrate**

    The install, architecture, integration and CI guides live on the main site,
    where they are maintained as one copy.

    [:octicons-arrow-right-24: Installation](https://victron-venus.github.io/#install)

- **Reference contracts**

    Service naming, MQTT topics and the shared release standard.

    [:octicons-arrow-right-24: Reference](reference/index.md)

</div>

## What this portal is

Each project page is generated from that project's `README.md` and `docs/`
directory. Nothing is copied into this repository, so there is no second copy to
drift: the project repository stays the source of truth, and this portal is a
reader over it. Relative links resolve to the repository's own blob view.

Documentation that is shared boilerplate — release workflow, quality evidence,
OpenSSF evidence, preflight and versioning notes — is not repeated per project.
Those live once in
[venus-os-ci-toolkit](https://github.com/victron-venus/venus-os-ci-toolkit).

The hand-written guides stay on [the main site](https://victron-venus.github.io/),
which is the single maintained copy. This portal does not duplicate them.

!!! note "Scope"
    A page here describes what a repository documents. It does not prove a
    deployment, a hardware test or a measured result. Verify claims against the
    project's own evidence before relying on them.
