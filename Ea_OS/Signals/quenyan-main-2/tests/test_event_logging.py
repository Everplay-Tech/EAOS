from qyn1.encoder import QYNEncoder
from qyn1.event_logging import EventPayloadClass
from qyn1.measurement import build_measurement_from_source


def test_event_logging_includes_string_indices():
    source = "def foo(x):\n    return x\n"
    result = build_measurement_from_source(source, file_id="test.py", encoder=QYNEncoder())

    identifier_events = [
        event
        for event in result.event_log.events
        if event.payload_class == EventPayloadClass.ID
    ]
    assert identifier_events, "expected at least one identifier payload to be recorded"
    assert all(event.string_index is not None for event in identifier_events)

    assert len(result.bits_per_token) == len(result.event_log.token_keys)
    assert "NONE" in result.payload_conditional_entropy
    assert result.tokens_section_bits > 0
    assert result.string_table_section_bits > 0
