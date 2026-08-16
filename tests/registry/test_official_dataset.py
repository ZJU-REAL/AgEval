"""Official Dataset plaza source: non-draft official-org database releases."""

from __future__ import annotations

from services.registry.official import is_official_dataset, official_dataset_ids
from services.registry.store import ReleaseRow, release_to_dict

from bora.registry.media_types import DATABASE_MEDIA_TYPE, PLUGIN_MEDIA_TYPE


def _row(
    *,
    database_id: str = "official/gaia-level1-15",
    version: str = "1.0.0",
    org_id: str | None = "official",
    media_type: str = DATABASE_MEDIA_TYPE,
) -> ReleaseRow:
    return ReleaseRow(
        database_id=database_id,
        version=version,
        visibility="public",
        package_digest="sha256:" + "a" * 64,
        blob_digest="sha256:" + "b" * 64,
        size=1,
        media_type=media_type,
        created_at=0.0,
        org_id=org_id,
    )


def test_official_non_draft_database_counts() -> None:
    rows = [_row()]
    assert is_official_dataset("official/gaia-level1-15", rows) is True
    assert official_dataset_ids(rows) == {"official/gaia-level1-15"}


def test_draft_only_is_not_official_dataset() -> None:
    rows = [_row(version="draft")]
    assert is_official_dataset("official/gaia-level1-15", rows) is False


def test_community_org_is_not_official_dataset() -> None:
    rows = [_row(database_id="acme/looks-official", org_id="acme")]
    assert is_official_dataset("acme/looks-official", rows) is False


def test_plugin_release_is_not_official_dataset() -> None:
    rows = [_row(database_id="official/sample-echo", media_type=PLUGIN_MEDIA_TYPE)]
    assert is_official_dataset("official/sample-echo", rows) is False


def test_other_database_id_does_not_qualify() -> None:
    rows = [_row()]
    assert is_official_dataset("official/other", rows) is False


def test_release_to_dict_marks_database_official() -> None:
    official = release_to_dict(_row())
    assert official["package_kind"] == "database"
    assert official["official"] is True
    community = release_to_dict(_row(org_id="acme"))
    assert community["official"] is False
    plugin = release_to_dict(_row(media_type=PLUGIN_MEDIA_TYPE, org_id="official"))
    assert plugin["package_kind"] == "plugin"
    assert plugin["official"] is True
