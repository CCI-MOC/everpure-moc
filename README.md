# Everpure MOC

This repository contains the configuration and documentation for Everpure storage integration with MOC OpenShift clusters.

## Documentation

- `docs/flashblade-setup.md` — Pure FlashBlade setup and storage configuration.
- `docs/portworx-setup.md` — Portworx installation and validation.
- `docs/storage-provisioning.md` — Filesystem and S3 provisioning guidance.
- `docs/pure1.md` — Pure1 guidance.
- `perf/README.md` — Performance testing documentation.
- `tests/README.md` — Verification and test guidance.

## Repository Layout

- `config/` — sample configuration files.
- `perf/` — performance tests and results.
- `tests/` — deployment manifests and verification assets.

## Getting Started

1. Read `docs/flashblade-setup.md`.
2. Read `docs/portworx-setup.md`.
3. Read `docs/storage-provisioning.md`.
4. Use `perf/README.md` and `tests/README.md` for validation.

### Troubleshooting

We ran into issues with `pvc`s created under portworx `storageClasses` mounting in `pod`s. In pod events this manifested as an `event` with the error message: "No valid backend found for ArrayID d663994a-a52c-49ac-bcff-2b4de120192d: not found". This may have been related to network asymmetry, though fixing the network issue was not an immediate fix. Eventually, bouncing the px-pure-csi-controller 'pods' one at a time in the portworx `namespace` did result in `pvc`s mounting and `pod`s creating. More info can be found in this [ticket](https://supportcenter.purestorage.com/cases/1f896c5f3b408f18b7a1c41864e45a2f).