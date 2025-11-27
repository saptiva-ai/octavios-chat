"""
Unit tests for SQL Validator

Tests cover:
    1. Forbidden keyword detection (DDL/DML)
    2. Table whitelist enforcement
    3. Suspicious pattern detection
    4. LIMIT injection for unbounded queries
    5. SELECT-only validation
"""

import pytest
from bankadvisor.services.sql_validator import SqlValidator, validate_sql


class TestSqlValidator:
    """Test suite for SqlValidator."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = SqlValidator(allowed_tables=["monthly_kpis"])

    # =========================================================================
    # HAPPY PATH TESTS
    # =========================================================================

    def test_valid_simple_select(self):
        """Test valid SELECT query passes validation."""
        sql = "SELECT fecha, imor FROM monthly_kpis WHERE banco_norm = 'INVEX'"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert result.sanitized_sql is not None
        assert "LIMIT" in result.sanitized_sql  # LIMIT should be injected

    def test_valid_select_with_limit(self):
        """Test SELECT with LIMIT passes without modification."""
        sql = "SELECT * FROM monthly_kpis LIMIT 100"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert result.sanitized_sql == sql  # No modification needed
        assert len(result.warnings) == 0

    def test_valid_select_with_aggregation(self):
        """Test aggregated query doesn't get LIMIT injected."""
        sql = "SELECT COUNT(*) FROM monthly_kpis GROUP BY banco_norm"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert "LIMIT" not in result.sanitized_sql
        assert len(result.warnings) == 0

    # =========================================================================
    # FORBIDDEN KEYWORDS TESTS
    # =========================================================================

    def test_reject_insert(self):
        """Test INSERT is rejected."""
        sql = "INSERT INTO monthly_kpis (fecha, imor) VALUES ('2024-01-01', 1.5)"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "INSERT" in result.error_message

    def test_reject_update(self):
        """Test UPDATE is rejected."""
        sql = "UPDATE monthly_kpis SET imor = 0"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "UPDATE" in result.error_message

    def test_reject_delete(self):
        """Test DELETE is rejected."""
        sql = "DELETE FROM monthly_kpis WHERE banco_norm = 'INVEX'"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "DELETE" in result.error_message

    def test_reject_drop(self):
        """Test DROP is rejected."""
        sql = "DROP TABLE monthly_kpis"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "DROP" in result.error_message

    def test_reject_create(self):
        """Test CREATE is rejected."""
        sql = "CREATE TABLE fake_table (id INT)"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "CREATE" in result.error_message

    def test_reject_alter(self):
        """Test ALTER is rejected."""
        sql = "ALTER TABLE monthly_kpis ADD COLUMN fake_col INT"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "ALTER" in result.error_message

    def test_reject_exec(self):
        """Test EXEC is rejected."""
        sql = "EXEC sp_malicious_proc"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "EXEC" in result.error_message

    def test_reject_union(self):
        """Test UNION is rejected."""
        sql = "SELECT * FROM monthly_kpis UNION SELECT * FROM users"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "UNION" in result.error_message

    def test_reject_comment_injection(self):
        """Test comment-based injection is rejected."""
        sql_variants = [
            "SELECT * FROM monthly_kpis -- malicious comment",
            "SELECT * FROM monthly_kpis /* malicious */ WHERE 1=1",
            "SELECT * FROM monthly_kpis # malicious",
        ]

        for sql in sql_variants:
            result = self.validator.validate(sql)
            assert result.valid is False, f"Should reject: {sql}"

    # =========================================================================
    # TABLE WHITELIST TESTS
    # =========================================================================

    def test_allowed_table_passes(self):
        """Test query with whitelisted table passes."""
        sql = "SELECT * FROM monthly_kpis"
        result = self.validator.validate(sql)

        assert result.valid is True

    def test_reject_non_whitelisted_table(self):
        """Test query with non-whitelisted table is rejected."""
        sql = "SELECT * FROM users"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "Invalid tables" in result.error_message
        assert "users" in result.error_message

    def test_reject_multiple_invalid_tables(self):
        """Test query with multiple non-whitelisted tables is rejected."""
        sql = "SELECT * FROM monthly_kpis JOIN users ON 1=1"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "users" in result.error_message

    # =========================================================================
    # SUSPICIOUS PATTERN TESTS
    # =========================================================================

    def test_reject_boolean_injection(self):
        """Test boolean injection (1=1) is rejected."""
        sql = "SELECT * FROM monthly_kpis WHERE 1=1 OR 2=2"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "Suspicious pattern" in result.error_message

    def test_reject_stacked_queries(self):
        """Test stacked queries are rejected."""
        sql = "SELECT * FROM monthly_kpis; DROP TABLE users"
        result = self.validator.validate(sql)

        assert result.valid is False
        # Should catch either the semicolon pattern or the DROP keyword

    # =========================================================================
    # SELECT-ONLY VALIDATION TESTS
    # =========================================================================

    def test_reject_non_select(self):
        """Test non-SELECT queries are rejected."""
        non_select_queries = [
            "SHOW TABLES",
            "DESCRIBE monthly_kpis",
            "EXPLAIN SELECT * FROM monthly_kpis",
        ]

        for sql in non_select_queries:
            result = self.validator.validate(sql)
            assert result.valid is False, f"Should reject: {sql}"
            assert "Only SELECT" in result.error_message

    # =========================================================================
    # SANITIZATION TESTS
    # =========================================================================

    def test_limit_injection_for_unbounded_query(self):
        """Test LIMIT is added to unbounded queries."""
        sql = "SELECT * FROM monthly_kpis WHERE banco_norm = 'INVEX'"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert "LIMIT 1000" in result.sanitized_sql
        assert any("LIMIT" in w for w in result.warnings)

    def test_no_limit_injection_for_aggregated_query(self):
        """Test LIMIT is NOT added to aggregated queries."""
        sql = "SELECT AVG(imor) FROM monthly_kpis"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert "LIMIT" not in result.sanitized_sql

    def test_limit_injection_handles_semicolon(self):
        """Test LIMIT injection handles queries ending with semicolon."""
        sql = "SELECT * FROM monthly_kpis;"
        result = self.validator.validate(sql)

        assert result.valid is True
        assert result.sanitized_sql.endswith(" LIMIT 1000;")

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_query_rejected(self):
        """Test empty query is rejected."""
        result = self.validator.validate("")

        assert result.valid is False
        assert "Empty" in result.error_message

    def test_whitespace_only_query_rejected(self):
        """Test whitespace-only query is rejected."""
        result = self.validator.validate("   \n  ")

        assert result.valid is False
        assert "Empty" in result.error_message

    def test_case_insensitive_keyword_detection(self):
        """Test forbidden keywords are detected case-insensitively."""
        sql_variants = [
            "DROP TABLE monthly_kpis",
            "drop table monthly_kpis",
            "DrOp TaBlE monthly_kpis",
        ]

        for sql in sql_variants:
            result = self.validator.validate(sql)
            assert result.valid is False, f"Should reject: {sql}"
            assert "DROP" in result.error_message.upper()

    def test_table_name_extraction_with_joins(self):
        """Test table names are extracted from JOIN clauses."""
        # This should fail because 'dim_banks' is not in whitelist
        sql = "SELECT * FROM monthly_kpis JOIN dim_banks ON 1=1"
        result = self.validator.validate(sql)

        assert result.valid is False
        assert "dim_banks" in result.error_message

    # =========================================================================
    # CONVENIENCE FUNCTION TESTS
    # =========================================================================

    def test_validate_sql_convenience_function(self):
        """Test standalone validate_sql() function."""
        sql = "SELECT * FROM monthly_kpis"
        result = validate_sql(sql, allowed_tables=["monthly_kpis"])

        assert result.valid is True

    def test_validate_sql_with_custom_tables(self):
        """Test convenience function with custom table list."""
        sql = "SELECT * FROM custom_table"
        result = validate_sql(sql, allowed_tables=["custom_table"])

        assert result.valid is True

        # Same query should fail with default tables
        result2 = validate_sql(sql, allowed_tables=["monthly_kpis"])
        assert result2.valid is False
