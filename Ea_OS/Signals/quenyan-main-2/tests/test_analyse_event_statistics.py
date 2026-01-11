from scripts import analyse_event_statistics as aes
from qyn1.event_logging import EventPayloadClass


def test_bit_allocation_reports_source_and_package_bytes() -> None:
    snapshot = aes.StatisticalSnapshot(
        token_count=2,
        string_payload_token_count=1,
        bits_tokens=16,
        bits_strings=8,
        package_bytes=3,
        source_bytes=1,
    )
    snapshot.payload_event_counter[EventPayloadClass.ID.value] = 1
    snapshot.payload_event_counter[EventPayloadClass.STR.value] = 1

    report = snapshot.bit_allocation_report()

    assert report["combined_bits_per_token"] == 12.0
    assert report["bits_per_source_byte"] == 24.0
    assert report["bytes_per_source_byte"] == 3.0


def test_compare_reports_marks_improvements() -> None:
    current = {
        "overall": {
            "entropy": {
                "H_T": 1.0,
                "H_joint": 1.5,
                "H_by_payload_class": {EventPayloadClass.ID.value: 0.4},
            },
            "bits": {
                "bits_per_token": 1.0,
                "bits_per_payload_token": 0.5,
                "combined_bits_per_token": 2.0,
                "bits_per_source_byte": 8.0,
                "bytes_per_source_byte": 0.25,
            },
        }
    }
    baseline = {
        "overall": {
            "entropy": {
                "H_T": 1.25,
                "H_joint": 1.75,
                "H_by_payload_class": {EventPayloadClass.ID.value: 0.6},
            },
            "bits": {
                "bits_per_token": 1.2,
                "bits_per_payload_token": 0.7,
                "combined_bits_per_token": 2.5,
                "bits_per_source_byte": 9.0,
                "bytes_per_source_byte": 0.3,
            },
        }
    }

    comparison = aes.compare_reports(current, baseline)
    overall = comparison["overall"]

    assert overall["entropy"]["token_entropy_improved"]
    assert overall["entropy"]["joint_entropy_improved"]
    assert overall["entropy"]["conditional_entropy"][EventPayloadClass.ID.value]["improved"]
    assert all(overall["bits"]["improved"].values())
