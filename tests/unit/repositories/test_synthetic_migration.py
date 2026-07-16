"""Migration contract tests for the Synthetic Dataset Generator schema (M4.1, T004).

Static text-contract tests over migrations/002_synthetic_datasets.sql: three tables,
nullable org_id on every table, child org-inheritance guards, indexes, RLS
enablement, and JWT-org policies from data-model.md. No live database is required.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = _REPO_ROOT / "migrations" / "002_synthetic_datasets.sql"


@pytest.fixture(scope="module")
def sql_text() -> str:
    if not _MIGRATION_PATH.exists():
        pytest.fail(f"Missing migration file: {_MIGRATION_PATH}")
    return _MIGRATION_PATH.read_text()


@pytest.fixture(scope="module")
def sql_lower(sql_text: str) -> str:
    return sql_text.lower()


class TestTablesExist:
    def test_synthetic_datasets_table(self, sql_lower):
        assert re.search(r"create table\s+synthetic_datasets", sql_lower)

    def test_synthetic_goldens_table(self, sql_lower):
        assert re.search(r"create table\s+synthetic_goldens", sql_lower)

    def test_synthetic_conversations_table(self, sql_lower):
        assert re.search(r"create table\s+synthetic_conversations", sql_lower)


class TestNullableOrgId:
    @pytest.mark.parametrize(
        "table_name",
        ["synthetic_datasets", "synthetic_goldens", "synthetic_conversations"],
    )
    def test_org_id_nullable(self, sql_lower, table_name):
        match = re.search(
            rf"create table\s+{table_name}\s*\((.*?)\n\);", sql_lower, re.DOTALL
        )
        assert match, f"Could not locate CREATE TABLE body for {table_name}"
        body = match.group(1)
        org_id_lines = [
            line for line in body.splitlines() if re.search(r"\borg_id\b", line)
        ]
        assert org_id_lines, f"No org_id column found for {table_name}"
        for line in org_id_lines:
            assert "not null" not in line, (
                f"org_id must remain nullable in {table_name}, got: {line!r}"
            )


class TestChildOrgInheritance:
    @pytest.mark.parametrize("table_name", ["synthetic_goldens", "synthetic_conversations"])
    def test_child_has_org_inheritance_trigger(self, sql_lower, table_name):
        assert re.search(
            rf"create trigger\s+\S*{table_name.replace('synthetic_', '')}\S*", sql_lower
        ) or re.search(rf"create trigger\s+\S*org\S*", sql_lower)
        assert f"before insert on {table_name}" in sql_lower or (
            re.search(rf"on\s+{table_name}\b", sql_lower) is not None
        )

    def test_inheritance_function_sets_and_rejects_mismatch(self, sql_lower):
        assert "new.org_id" in sql_lower
        assert "raise exception" in sql_lower or "raise_exception" in sql_lower


class TestIndexes:
    def test_org_id_indexed(self, sql_lower):
        assert re.search(r"create index.*org_id", sql_lower)

    def test_parent_fk_indexed(self, sql_lower):
        assert re.search(r"create index.*dataset_id", sql_lower)

    def test_bot_id_indexed(self, sql_lower):
        assert re.search(r"create index.*bot_id", sql_lower)

    def test_indexing_status_indexed(self, sql_lower):
        assert re.search(r"create index.*indexing_status", sql_lower)


class TestRLS:
    @pytest.mark.parametrize(
        "table_name",
        ["synthetic_datasets", "synthetic_goldens", "synthetic_conversations"],
    )
    def test_rls_enabled(self, sql_lower, table_name):
        assert f"alter table {table_name} enable row level security" in sql_lower

    @pytest.mark.parametrize(
        "table_name",
        ["synthetic_datasets", "synthetic_goldens", "synthetic_conversations"],
    )
    def test_select_policy_uses_jwt_org(self, sql_lower, table_name):
        pattern = (
            rf"create policy.*on\s+{table_name}.*for\s+select.*"
            r"app_metadata.*org_id"
        )
        assert re.search(pattern, sql_lower, re.DOTALL)

    @pytest.mark.parametrize(
        "table_name",
        ["synthetic_datasets", "synthetic_goldens", "synthetic_conversations"],
    )
    def test_insert_policy_has_with_check(self, sql_lower, table_name):
        pattern = rf"create policy.*on\s+{table_name}.*for\s+insert.*with check"
        assert re.search(pattern, sql_lower, re.DOTALL)

    @pytest.mark.parametrize(
        "table_name",
        ["synthetic_datasets", "synthetic_goldens", "synthetic_conversations"],
    )
    def test_update_policy_has_with_check(self, sql_lower, table_name):
        pattern = rf"create policy.*on\s+{table_name}.*for\s+update.*with check"
        assert re.search(pattern, sql_lower, re.DOTALL)

    def test_no_delete_policy(self, sql_lower):
        assert "for delete" not in sql_lower
