# services/iso-validator

Java 21 sidecar cross-validator using prowide-iso20022; parses every archived message in CI and flags disagreement with the Python path.

Defined in SPEC §6.2 as a Java 21 sidecar using prowide-iso20022 (Apache-2.0).

The Python path (`xmlschema`, milestone M1) is the validator CI runs. Maven Central's newest `com.prowidesoftware:pw-iso20022` at the time of M3 is `SRU2024-10.2.7`. The SRU2025-10.4 line named in SPEC §6.2 is not published there, so this sidecar is not wired and no prowide jar is vendored. When that line is published, a sidecar can parse the switch archive and fail the run if it disagrees with `agentbank_iso`.
