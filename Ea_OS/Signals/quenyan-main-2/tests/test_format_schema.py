import pytest
from hypothesis import given, strategies as st

from qyn1.format import (
    HeaderFormatError,
    PayloadHeader,
    Section,
    WrapperHeader,
    WRAPPER_MAGIC,
    decode_frame,
    decode_sections,
    encode_frame,
    encode_sections,
    validate_frame,
    validate_sections,
)
from qyn1.versioning import Version


def test_envelope_headers_round_trip_and_magic_validation():
    version = Version(1, 2, 3)
    body = b"{}"
    header = WrapperHeader(WRAPPER_MAGIC, version, len(body))
    buffer = header.encode() + body + b"extra"

    parsed, remainder = WrapperHeader.parse(buffer)
    assert parsed == header

    payload, trailing = parsed.split_body(remainder)
    assert payload == body
    assert trailing == b"extra"

    with pytest.raises(HeaderFormatError):
        PayloadHeader.parse(buffer)


@given(
    body=st.binary(max_size=64),
    major=st.integers(min_value=0, max_value=5),
    minor=st.integers(min_value=0, max_value=5),
    patch=st.integers(min_value=0, max_value=5),
    features=st.lists(
        st.sampled_from(
            [
                "compression:optimisation",
                "compression:extras",
                "payload:source-map",
                "compression:fse",
            ]
        ),
        unique=True,
        max_size=4,
    ),
)
@pytest.mark.property
def test_frame_round_trip_validates(body, major, minor, patch, features):
    version = Version(major, minor, patch)
    encoded = encode_frame(
        magic=WRAPPER_MAGIC,
        version=version,
        features=features,
        body=body,
    )

    frame, remainder = decode_frame(encoded, expected_magic=WRAPPER_MAGIC)
    assert remainder == b""
    validated = validate_frame(frame, expected_magic=WRAPPER_MAGIC)

    assert validated.body == body
    assert validated.version == version
    assert validated.features == frozenset(features)


@given(
    sections=st.lists(
        st.builds(
            Section,
            identifier=st.integers(min_value=0, max_value=0xFFFF),
            flags=st.integers(min_value=0, max_value=0xFFFF),
            payload=st.binary(max_size=64),
        ),
        min_size=1,
        max_size=5,
    )
)
@pytest.mark.property
def test_sections_round_trip_validates(sections):
    encoded = encode_sections(sections)
    decoded = tuple(validate_sections(decode_sections(encoded)))

    assert [
        (section.identifier, section.flags, section.payload) for section in decoded
    ] == [
        (section.identifier, section.flags, section.payload) for section in sections
    ]
