"""Tests: product master import parsing, validation, idempotency."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    IngestionEntity,
    IngestionRejection,
    IngestionRun,
    IngestionSourceType,
    IngestionStatus,
    Product,
    ProductMasterStage,
    Supplier,
    SupplierProduct,
)
from app.services.import_product_master import (
    _get,
    _get_optional,
    _get_sku_code,
    _is_recipe_yes,
    _normalize_aah_code,
    _parse_decimal,
    _parse_leadtime_weeks,
    import_from_stage,
    validate_and_stage_row,
)


def test_parse_leadtime_weeks() -> None:
    """Leadtime '8 weeks' and '12' parse correctly."""
    ok, val, msg = _parse_leadtime_weeks("8 weeks")
    assert ok is True
    assert val == 8
    assert msg == ""
    ok, val, msg = _parse_leadtime_weeks("12 weeks")
    assert ok is True
    assert val == 12
    ok, val, _ = _parse_leadtime_weeks("12")
    assert ok is True
    assert val == 12
    ok, val, _ = _parse_leadtime_weeks("")
    assert ok is True
    assert val is None
    ok, val, _ = _parse_leadtime_weeks("NA")
    assert ok is True
    assert val is None
    ok, val, msg = _parse_leadtime_weeks("invalid")
    assert ok is False
    assert val is None
    assert "not parseable" in msg


def test_na_aah_code_becomes_none() -> None:
    """AAH code NA/N/A/-/null (case-insensitive) or blank becomes NULL via _normalize_aah_code."""
    assert _normalize_aah_code("NA") is None
    assert _normalize_aah_code("na") is None
    assert _normalize_aah_code("N/A") is None
    assert _normalize_aah_code("n/a") is None
    assert _normalize_aah_code("-") is None
    assert _normalize_aah_code("null") is None
    assert _normalize_aah_code("NULL") is None
    assert _normalize_aah_code("") is None
    assert _normalize_aah_code("   ") is None
    assert _normalize_aah_code(None) is None
    assert _normalize_aah_code("AAH001") == "AAH001"
    assert _normalize_aah_code("  AAH002  ") == "AAH002"


def test_is_recipe_yes() -> None:
    """AYMES Recipe Y/N parsing."""
    assert _is_recipe_yes("Y") is True
    assert _is_recipe_yes("Yes") is True
    assert _is_recipe_yes("N") is False
    assert _is_recipe_yes("") is False
    assert _is_recipe_yes("n") is False


def test_get_trim_preserve_case() -> None:
    """_get trims whitespace and preserves original case."""
    row = {"SKU code": "  SKU001  ", "Supplier": "Sup1"}
    assert _get(row, "SKU code") == "SKU001"
    assert _get(row, "Supplier") == "Sup1"


def test_sku_code_trimming_preserves_case() -> None:
    """_get_sku_code trims whitespace and preserves case; blank after trim is empty."""
    assert _get_sku_code({"SKU code": "  SKU001  "}) == "SKU001"
    assert _get_sku_code({"SKU code": "MySku"}) == "MySku"
    assert _get_sku_code({"SKU code": "  "}) == ""
    assert _get_sku_code({"SKU code": ""}) == ""
    assert _get_sku_code({"SKU code": None}) == ""


def test_sku_whitespace_trimming_prevents_duplicate_products(db_session) -> None:
    """SKU code whitespace trimming: '  SKU1  ' and 'SKU1' resolve to same product (one row, no duplicate)."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=2,
            payload={
                "Supplier": "SUP-T",
                "SKU code": "  SKU-TRIM  ",
                "Description": "Product with trimmed SKU",
            },
        )
    )
    db_session.commit()
    import_from_stage(db_session, run_id)
    db_session.commit()
    products = db_session.query(Product).filter(Product.sku == "SKU-TRIM").all()
    assert len(products) == 1
    assert products[0].sku == "SKU-TRIM"
    # Re-import same logical SKU with different whitespace: still one product (upsert by sku)
    run_id2 = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id2,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id2,
            row_number=2,
            payload={
                "Supplier": "SUP-T",
                "SKU code": "SKU-TRIM",
                "Description": "Product with trimmed SKU (updated)",
            },
        )
    )
    db_session.commit()
    import_from_stage(db_session, run_id2)
    db_session.commit()
    products_after = db_session.query(Product).filter(Product.sku == "SKU-TRIM").all()
    assert len(products_after) == 1
    assert products_after[0].name == "Product with trimmed SKU (updated)"


def test_duplicate_aah_code_across_different_skus_allowed(db_session) -> None:
    """Duplicate AAH code across different SKUs is allowed (aah_code is reference only, not unique)."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=2,
        )
    )
    db_session.commit()
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=2,
            payload={
                "Supplier": "SUP-X",
                "SKU code": "SKU-X1",
                "Description": "Product X1",
                "AAH code": "SHARED-AAH",
            },
        )
    )
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=3,
            payload={
                "Supplier": "SUP-X",
                "SKU code": "SKU-X2",
                "Description": "Product X2",
                "AAH code": "SHARED-AAH",
            },
        )
    )
    db_session.commit()
    import_from_stage(db_session, run_id)
    db_session.commit()
    p1 = db_session.query(Product).filter(Product.sku == "SKU-X1").first()
    p2 = db_session.query(Product).filter(Product.sku == "SKU-X2").first()
    assert p1 is not None and p2 is not None
    assert p1.aah_code == "SHARED-AAH" and p2.aah_code == "SHARED-AAH"
    assert p1.sku != p2.sku


def test_parse_decimal() -> None:
    """Decimal parsing; NA/blank -> None."""
    ok, val, _ = _parse_decimal("1.50")
    assert ok is True
    assert val == Decimal("1.50")
    ok, val, _ = _parse_decimal("NA")
    assert ok is True
    assert val is None
    ok, val, msg = _parse_decimal("x")
    assert ok is False
    assert val is None
    assert "Invalid" in msg


@pytest.fixture
def db_session():
    """In-memory SQLite session for import tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_validate_rejects_missing_sku(db_session) -> None:
    """Rows with missing SKU code are rejected and captured with row_number + reason."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    row = {"Supplier": "SUP1", "SKU code": "", "Description": "A product"}
    staged, reason = validate_and_stage_row(db_session, run_id, row, row_number=2)
    assert staged is False
    assert "SKU code required" in reason
    db_session.commit()
    rej = db_session.query(IngestionRejection).filter(IngestionRejection.ingestion_run_id == run_id).first()
    assert rej is not None
    assert rej.row_number == 2
    assert "SKU code required" in rej.reason
    assert rej.raw_payload == row


def test_validate_allows_missing_supplier_stages_row(db_session) -> None:
    """Supplier is optional at validate time; import_from_stage uses code DEFAULT when blank."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    row = {"Supplier": "", "SKU code": "SKU-NOSUP", "Description": "A product"}
    staged, reason = validate_and_stage_row(db_session, run_id, row, row_number=3)
    assert staged is True
    assert reason == ""


def test_validate_rejects_blank_description(db_session) -> None:
    """Rows with blank Description are rejected."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    row = {"Supplier": "SUP1", "SKU code": "SKU1", "Description": "   "}
    staged, reason = validate_and_stage_row(db_session, run_id, row, row_number=4)
    assert staged is False
    assert "Description" in reason


def test_validate_stages_valid_row(db_session) -> None:
    """Valid row is staged to product_master_stage."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    row = {
        "Supplier": "SUP1",
        "SKU code": "SKU1",
        "Description": "Product One",
        "Supplier Leadtime": "8 weeks",
        "Single Units_MOQ": "100",
        "Incremental Qty (Single Units)": "12",
    }
    staged, reason = validate_and_stage_row(db_session, run_id, row, row_number=5)
    assert staged is True
    assert reason == ""
    db_session.commit()
    stage_row = db_session.query(ProductMasterStage).filter(ProductMasterStage.ingestion_run_id == run_id).first()
    assert stage_row is not None
    assert stage_row.row_number == 5
    assert stage_row.payload["SKU code"] == "SKU1"
    assert stage_row.payload["Supplier"] == "SUP1"


def test_import_creates_suppliers_products_links(db_session) -> None:
    """import_from_stage creates supplier, product, supplier_product, and product_master_attributes."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=2,
            payload={
                "Supplier": "SUP-A",
                "SKU code": "SKU-A1",
                "Description": "Product A",
                "AAH code": "AAH-A1",
                "Supplier Leadtime": "8 weeks",
                "Single Units_MOQ": "100",
                "Incremental Qty (Single Units)": "12",
                "AYMES Recipe (Y/N)": "N",
            },
        )
    )
    db_session.commit()
    inserted, updated = import_from_stage(db_session, run_id)
    db_session.commit()
    assert inserted >= 1
    supplier = db_session.query(Supplier).filter(Supplier.code == "SUP-A").first()
    assert supplier is not None
    product = db_session.query(Product).filter(Product.sku == "SKU-A1").first()
    assert product is not None
    assert product.name == "Product A"
    assert product.aah_code == "AAH-A1"
    link = (
        db_session.query(SupplierProduct)
        .filter(SupplierProduct.supplier_id == supplier.id, SupplierProduct.product_id == product.id)
        .first()
    )
    assert link is not None
    assert link.lead_time_weeks == 8
    assert link.moq_units == 100
    assert link.pack_size_units == 12


def test_reimport_does_not_duplicate(db_session) -> None:
    """Re-importing same row (same SKU + Supplier) updates existing, does not duplicate."""
    run_id = uuid4()
    db_session.add(
        IngestionRun(
            id=run_id,
            source_type=IngestionSourceType.CSV,
            entity=IngestionEntity.PRODUCT_MASTER,
            status=IngestionStatus.PENDING,
            row_count=1,
        )
    )
    db_session.commit()
    db_session.add(
        ProductMasterStage(
            ingestion_run_id=run_id,
            row_number=2,
            payload={
                "Supplier": "SUP-B",
                "SKU code": "SKU-B1",
                "Description": "Product B first",
                "Supplier Leadtime": "4 weeks",
            },
        )
    )
    db_session.commit()
    ins1, upd1 = import_from_stage(db_session, run_id)
    db_session.commit()
    product_count_after_first = db_session.query(Product).filter(Product.sku == "SKU-B1").count()
    assert product_count_after_first == 1
    # Same run_id - stage has one row; run again (simulate re-execute)
    ins2, upd2 = import_from_stage(db_session, run_id)
    db_session.commit()
    product_count_after_second = db_session.query(Product).filter(Product.sku == "SKU-B1").count()
    assert product_count_after_second == 1
    product = db_session.query(Product).filter(Product.sku == "SKU-B1").first()
    assert product is not None
    assert product.name == "Product B first"
