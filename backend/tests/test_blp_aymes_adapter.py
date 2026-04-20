"""Tests: BLP-AYMES Report adapter — format detection, normalization, aggregation, EXPIRING, invalid values."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest  # type: ignore[reportMissingImports]

from app.ingestion.soh.adapters.blp_aymes_report import (
    aggregate,
    is_blp_aymes_format,
    normalize,
)
from app.services.csv_import import read_csv


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "blp_aymes_report.csv"


def test_is_blp_aymes_format() -> None:
    assert is_blp_aymes_format(["Code", "Description", "Balance", "Location", "Expiry Date"]) is True
    assert is_blp_aymes_format(["code", "balance"]) is True
    assert is_blp_aymes_format(["Code", "Balance", "Extra"]) is True
    assert is_blp_aymes_format(["Branch Name", "AAH Code", "STOCK"]) is False
    assert is_blp_aymes_format(["Code"]) is False
    assert is_blp_aymes_format(["Balance"]) is False


def test_normalize_valid_row() -> None:
    row = {"Code": "AC1.5-CH", "Description": "Product A", "Balance": "71", "Location": "LOC-A", "Expiry Date": "01/02/2026"}
    nr = normalize(row, 2)
    assert nr.sku == "AC1.5-CH"
    assert nr.qty_on_hand == 71
    assert nr.expiry_date == date(2026, 2, 1)
    assert nr.expiry_status is None
    assert nr.bin_location == "LOC-A"
    assert nr.reject_reason is None


def test_normalize_expiring() -> None:
    row = {"Code": "AC1.5-CH", "Balance": "1416", "Expiry Date": "EXPIRING"}
    nr = normalize(row, 3)
    assert nr.sku == "AC1.5-CH"
    assert nr.qty_on_hand == 1416
    assert nr.expiry_date is None
    assert nr.expiry_status == "EXPIRING"
    assert nr.reject_reason is None


def test_normalize_expiring_case_insensitive() -> None:
    row = {"Code": "X", "Balance": "1", "Expiry Date": "expiring"}
    nr = normalize(row, 2)
    assert nr.expiry_status == "EXPIRING"


def test_normalize_blank_balance() -> None:
    row = {"Code": "SKU-X", "Balance": "", "Location": "LOC-X"}
    nr = normalize(row, 2)
    assert nr.qty_on_hand == 0
    assert nr.reject_reason is None


def test_normalize_invalid_balance() -> None:
    row = {"Code": "SKU-BAD", "Balance": "not-a-number"}
    nr = normalize(row, 2)
    assert nr.reject_reason == "Invalid number"


def test_normalize_empty_code() -> None:
    row = {"Code": "", "Balance": "0"}
    nr = normalize(row, 2)
    assert nr.reject_reason == "Code required"


def test_normalize_invalid_date_does_not_reject() -> None:
    row = {"Code": "SKU-INVALID-DATE", "Balance": "20", "Expiry Date": "99/99/9999"}
    nr = normalize(row, 2)
    assert nr.reject_reason is None
    assert nr.qty_on_hand == 20
    assert nr.expiry_date is None


def test_aggregate_sums_by_sku() -> None:
    rows = [
        {"Code": "AC1.5-CH", "Balance": "71"},
        {"Code": "AC1.5-CH", "Balance": "312"},
        {"Code": "AC1.5-CH", "Balance": "1416"},
    ]
    normalized = [normalize(r, i) for i, r in enumerate(rows, start=2)]
    result = aggregate(normalized, date(2025, 2, 24), "BLP")
    by_sku = {sku: qty for (wh, sku, sd, qty) in result}
    assert by_sku["AC1.5-CH"] == 71 + 312 + 1416


def test_aggregate_excludes_rejected() -> None:
    rows = [
        {"Code": "OK", "Balance": "10"},
        {"Code": "BAD", "Balance": "not-a-number"},
    ]
    normalized = [normalize(r, i) for i, r in enumerate(rows, start=2)]
    result = aggregate(normalized, date(2025, 2, 24), "BLP")
    skus = [sku for (_, sku, _, _) in result]
    assert "OK" in skus
    assert "BAD" not in skus


def test_fixture_file_aggregation() -> None:
    content = FIXTURE_PATH.read_bytes()
    rows = read_csv(content)
    assert len(rows) >= 5
    headers = list(rows[0].keys())
    assert is_blp_aymes_format(headers) is True
    normalized = [normalize(r, i) for i, r in enumerate(rows, start=2)]
    result = aggregate(normalized, date(2025, 2, 24), "BLP")
    by_sku = {sku: qty for (wh, sku, sd, qty) in result}
    assert "AC1.5-CH" in by_sku
    assert by_sku["AC1.5-CH"] == 71 + 312 + 1416
    assert "SKU-X" in by_sku
    assert by_sku["SKU-X"] == 10 + 5
    assert "SKU-BAD" not in by_sku
    assert "" not in by_sku
    assert "SKU-INVALID-DATE" in by_sku
    assert by_sku["SKU-INVALID-DATE"] == 20
