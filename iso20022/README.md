# iso20022

Official ISO 20022 XML schemas for the SPEC §6.1 message set, plus
`xsd/MANIFEST.yaml` (filename, version, SHA-256, catalogue URL, what the
testbed uses the message for).

## The schemas are fetched, not committed

`iso20022/xsd/*.xsd` is git-ignored. Redistribution terms for the schema files
on the ISO 20022 site are unclear (SPEC §17: ship only what may be
redistributed; if that is not clearly allowed, `make bootstrap` / `make
iso-setup` downloads them). This repository therefore records the exact
upstream bytes by hash and downloads them at build time. FedNow and RTP usage
guidelines on SWIFT MyStandards are member-gated and are **not** fetched or
redistributed (SPEC §6.2, §17). The switch's own usage rules live in
`config/switch/usage_rules.yaml`.

### Source statement

The schemas are the ISO 20022 message definitions published by the ISO 20022
Registration Authority:

> ISO 20022 message definitions, © ISO. Source: the ISO 20022 message catalogue
> at <https://www.iso20022.org/iso-20022-message-definitions>. Schema files are
> retrieved from the official catalogue URLs under
> `https://www.iso20022.org/sites/default/files/documents/messages/`
> (one URL per message, recorded as `source_url` in `xsd/MANIFEST.yaml`).
> ISO 20022 is a registered trademark of ISO. These files are used here as
> published; they are not modified.

Each `source_url` in the manifest points at that catalogue. A download is kept
only when its SHA-256 equals the manifest entry.

## Verify

Offline, after a download (recomputes SHA-256 of the local files):

```sh
make xsd-verify
# python3 scripts/fetch_xsd.py verify
```

Re-download into a temporary directory and compare hashes, without touching
the working copies (needs network):

```sh
make xsd-fetch
# python3 scripts/fetch_xsd.py fetch
```

`make xsd-install` (`scripts/fetch_xsd.py install`) downloads any missing or
mismatched file from its `source_url` and writes it only after the hash
matches.

## Regenerate the bindings

```sh
make iso-setup    # xsd-install, then iso-gen
make iso-gen      # xsdata only; XSDs must already be present
```

`scripts/gen_iso_bindings.sh` runs the pinned `xsdata` (26.10, MIT) once per
message:

```text
xsdata generate iso20022/xsd/<message>.xsd --package agentbank_iso.gen.<package>
```

Output is `libs/agentbank_iso/src/agentbank_iso/gen/`, also git-ignored.
Generation is deterministic for a given XSD hash and xsdata version. The
library API on top of those bindings is documented in
[`libs/agentbank_iso/README.md`](../libs/agentbank_iso/README.md).

`make test` refuses to start when the bindings are absent and tells you to run
`make iso-setup`. CI does that before lint, typecheck and pytest, then runs
`make xsd-verify`.
