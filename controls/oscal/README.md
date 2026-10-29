# OSCAL baselines

`NIST_SP-800-53_rev5_{LOW,MODERATE,HIGH}-baseline_profile.json` are the
Release 5.2.0 baseline profiles from
[usnistgov/oscal-content](https://github.com/usnistgov/oscal-content)
(`nist.gov/SP800-53/rev5/json/`). NIST publications are public domain in
the United States. `controls/check_baselines.py` reads them. They are
vendored so the check runs without a network call.
