"""M1 acceptance: Hypothesis round-trip for every SPEC §6.1 message.

For each message a valid domain model is generated, built to XML, validated
against the XSD, parsed back and compared to the original; the serialisation is
also asserted byte-stable. The ``ci`` profile runs 1,000 examples per message;
the guard below fails loudly if the active profile would drop below that, so the
acceptance criterion cannot silently regress.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from iso_strategies import ROUND_TRIP_CASES, RoundTripCase  # type: ignore[import-not-found]

from agentbank_iso.validate import validate_xsd


def test_ci_profile_runs_at_least_1000_examples() -> None:
    profile = os.environ.get("HYPOTHESIS_PROFILE", "ci")
    if profile == "ci":
        assert settings().max_examples >= 1000, (
            "the ci/default Hypothesis profile must run >= 1000 examples per message"
        )


def test_every_message_has_a_round_trip_case() -> None:
    from agentbank_iso.messages import all_message_ids

    covered = {case.message_id for case in ROUND_TRIP_CASES}
    assert covered == set(all_message_ids())


@pytest.mark.parametrize("case", ROUND_TRIP_CASES, ids=lambda c: c.message_id)
def test_round_trip(case: RoundTripCase) -> None:
    executed = 0

    @given(model=case.strategy)
    def check(model: object) -> None:
        nonlocal executed
        executed += 1
        xml = case.build(model)

        result = validate_xsd(xml, case.message_id)
        assert result.ok, (case.message_id, [i.__dict__ for i in result.issues])

        parsed = case.parse(xml)
        assert parsed == model

        # Re-serialising the parsed model reproduces the exact bytes.
        assert case.build(parsed) == xml

    check()
    # Every generated example must have run the full build/validate/parse cycle.
    assert executed >= settings().max_examples, (case.message_id, executed)


@given(data=st.data())
def test_generic_to_xml_from_xml(data: st.DataObject) -> None:
    """The generic to_xml/from_xml helpers agree with the typed builders."""
    from agentbank_iso import from_xml, to_xml

    case = data.draw(st.sampled_from(ROUND_TRIP_CASES))
    model = data.draw(case.strategy)
    xml = case.build(model)
    document = from_xml(xml, case.message_id)
    assert to_xml(document) == xml
