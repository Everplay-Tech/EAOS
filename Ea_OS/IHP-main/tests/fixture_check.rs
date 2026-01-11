mod fixture_inputs;

use std::fs;

#[test]
fn capsule_fixture_matches_expected_hex() {
    let regenerated =
        fixture_inputs::generate_fixture_capsule_hex().expect("regenerated fixture capsule");
    let expected =
        fs::read_to_string("tests/fixtures/capsule_v1.hex").expect("read fixture hex file");
    let expected = expected.trim();

    assert_eq!(
        regenerated, expected,
        "capsule_v1.hex no longer matches the deterministic fixture; regenerate if the protocol intentionally changed"
    );
}
