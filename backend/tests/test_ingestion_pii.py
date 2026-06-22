"""Ingestion + the PII boundary — the privacy-critical contract."""

from __future__ import annotations

import pandas as pd

from margadrishti.ingestion.violations import PII_COLUMNS, load_violations

RAW = """id,latitude,longitude,location,vehicle_number,vehicle_type,description,violation_type,offence_code,created_datetime,closed_datetime,modified_datetime,device_id,created_by_id,center_code,police_station,data_sent_to_scita,junction_name,action_taken_timestamp,data_sent_to_scita_timestamp,updated_vehicle_number,updated_vehicle_type,validation_status,validation_timestamp
FKID0,12.93,77.62,"Koramangala",KA01AB1234,CAR,,"[""WRONG PARKING""]","[112]",2023-11-20 00:28:46+00,,,DEV1,OFF1,9,Madiwala,TRUE,No Junction,,,,,approved,
FKID1,12.90,77.70,"HSR",KA02CD5678,CAR,,"[""NO PARKING""]","[113]",2023-11-24 22:46:46+00,,,DEV2,OFF2,82,Bellandur,FALSE,No Junction,,,,,,
FKID2,0,0,"bad",KA03,CAR,,"[""WRONG PARKING""]","[112]",2023-11-20 00:27:46+00,,,DEV1,OFF1,9,Madiwala,TRUE,No Junction,,,,,rejected,
"""


def test_pii_split_and_normalisation(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text(RAW, encoding="utf-8")
    res = load_violations(str(p))

    # The 0,0 row is dropped as invalid geometry.
    assert res.n_rows == 2 and res.n_dropped == 1

    # No PII column ever appears in the analytics-safe frame.
    for col in PII_COLUMNS:
        assert col not in res.safe.columns
    assert "vehicle_number" not in res.safe.columns

    # PII lives only in the restricted frame, keyed by record_id.
    assert set(["record_id", *PII_COLUMNS]).issubset(res.restricted.columns)
    assert (res.restricted["vehicle_number"] == "KA01AB1234").any()

    # Pseudonymous refs are present, stable, and NOT the raw id.
    row0 = res.safe[res.safe.record_id == "FKID0"].iloc[0]
    assert row0["officer_ref"] and row0["officer_ref"] != "OFF1"
    assert row0["device_ref"] and row0["device_ref"] != "DEV1"

    # Timestamps tz-aware UTC; validation normalised (missing → unvalidated).
    assert str(res.safe["observed_at_utc"].dt.tz) == "UTC"
    statuses = set(res.safe["validation_status"])
    assert statuses <= {"approved", "rejected", "unvalidated"}
    assert (res.safe[res.safe.record_id == "FKID1"]["validation_status"] == "unvalidated").all()


def test_pseudonymisation_is_deterministic(tmp_path):
    p = tmp_path / "v.csv"
    p.write_text(RAW, encoding="utf-8")
    a = load_violations(str(p)).safe.set_index("record_id")["officer_ref"]
    b = load_violations(str(p)).safe.set_index("record_id")["officer_ref"]
    pd.testing.assert_series_equal(a, b)
