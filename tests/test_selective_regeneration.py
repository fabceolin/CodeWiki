"""
Unit tests for selective module regeneration functionality.

Tests cover:
- should_process_module() matching logic
- get_required_parents() parent extraction
- Edge cases for module filtering
"""

import pytest
from typing import Set

from codewiki.src.be.documentation_generator import (
    should_process_module,
    get_required_parents,
)


# Test data: Standard module tree structure
MODULE_TREE = [
    "backend",
    "backend/auth",
    "backend/auth/login",
    "backend/auth/register",
    "backend/api",
    "backend/api/handlers",
    "utils",
    "utils/validation",
    "core",
    "core/db",
    "core/db/models",
    "core/db/migrations",
]

ALL_MODULE_KEYS = set(MODULE_TREE)


class TestShouldProcessModule:
    """Tests for should_process_module() function."""

    # SMR-UNIT-006: Exact match
    def test_exact_match(self):
        """Test exact match: filter 'backend/auth' matches module 'backend/auth'."""
        result, reason = should_process_module(
            "backend/auth", ["backend/auth"], ALL_MODULE_KEYS
        )
        assert result is True
        assert "exact match" in reason
        assert "backend/auth" in reason

    # SMR-UNIT-007: Prefix match (child of specified)
    def test_prefix_match_child_of(self):
        """Test prefix match: filter 'backend/auth' matches module 'backend/auth/login'."""
        result, reason = should_process_module(
            "backend/auth/login", ["backend/auth"], ALL_MODULE_KEYS
        )
        assert result is True
        assert "child of" in reason
        assert "backend/auth" in reason

    # SMR-UNIT-008: Parent match (parent of specified)
    def test_parent_match(self):
        """Test parent match: filter 'backend/auth/login' matches module 'backend/auth'."""
        result, reason = should_process_module(
            "backend/auth", ["backend/auth/login"], ALL_MODULE_KEYS
        )
        assert result is True
        assert "parent of" in reason
        assert "backend/auth/login" in reason

    # SMR-UNIT-009: No match
    def test_no_match(self):
        """Test no match: filter 'backend/auth' does not match module 'utils'."""
        result, reason = should_process_module(
            "utils", ["backend/auth"], ALL_MODULE_KEYS
        )
        assert result is False
        assert "not in filter" in reason

    # SMR-UNIT-010: Boundary check - no false prefix match
    def test_no_false_prefix_match(self):
        """Test boundary: filter 'backend' does NOT match module 'backend-utils'."""
        # 'backend' should match 'backend/auth' but NOT 'backend-utils'
        all_keys = ALL_MODULE_KEYS | {"backend-utils"}

        result, reason = should_process_module(
            "backend-utils", ["backend"], all_keys
        )
        assert result is False
        assert "not in filter" in reason

    def test_no_filter_returns_true(self):
        """Test that empty/None filter returns True with 'no filter' reason."""
        result, reason = should_process_module("backend/auth", None, ALL_MODULE_KEYS)
        assert result is True
        assert reason == "no filter"

        result, reason = should_process_module("backend/auth", [], ALL_MODULE_KEYS)
        assert result is True
        assert reason == "no filter"

    def test_multiple_filters_first_match_wins(self):
        """Test with multiple filter patterns."""
        result, reason = should_process_module(
            "backend/auth/login",
            ["utils", "backend/auth"],
            ALL_MODULE_KEYS
        )
        assert result is True
        assert "backend/auth" in reason

    def test_root_module_as_filter(self):
        """Test root module 'backend' matches all children."""
        # backend/auth/login should match filter "backend"
        result, reason = should_process_module(
            "backend/auth/login", ["backend"], ALL_MODULE_KEYS
        )
        assert result is True
        assert "child of" in reason

    def test_deep_nesting(self):
        """Test deep nesting: 4+ level modules."""
        deep_keys = ALL_MODULE_KEYS | {"core/db/models/user", "core/db/models/user/profile"}

        # Filter on mid-level should include deep children
        result, reason = should_process_module(
            "core/db/models/user/profile", ["core/db/models"], deep_keys
        )
        assert result is True
        assert "child of" in reason

        # Deep filter should include mid-level parents
        result, reason = should_process_module(
            "core/db", ["core/db/models/user/profile"], deep_keys
        )
        assert result is True
        assert "parent of" in reason


class TestGetRequiredParents:
    """Tests for get_required_parents() function."""

    # SMR-UNIT-011: Parents of deeply nested path
    def test_parents_of_deep_path(self):
        """Test parents of 'a/b/c/d' returns {'a', 'a/b', 'a/b/c'}."""
        parents = get_required_parents(["a/b/c/d"])
        assert parents == {"a", "a/b", "a/b/c"}

    def test_parents_of_single_level(self):
        """Test parents of 'backend' returns empty set."""
        parents = get_required_parents(["backend"])
        assert parents == set()

    def test_parents_of_two_level(self):
        """Test parents of 'backend/auth' returns {'backend'}."""
        parents = get_required_parents(["backend/auth"])
        assert parents == {"backend"}

    def test_parents_of_multiple_paths(self):
        """Test parents of multiple paths combines all parent paths."""
        parents = get_required_parents(["backend/auth/login", "utils/validation"])
        expected = {"backend", "backend/auth", "utils"}
        assert parents == expected

    def test_parents_empty_list(self):
        """Test parents of empty list returns empty set."""
        parents = get_required_parents([])
        assert parents == set()

    def test_parents_no_duplicates(self):
        """Test that overlapping paths don't cause duplicates."""
        parents = get_required_parents(["backend/auth/login", "backend/auth/register"])
        # Both share 'backend' and 'backend/auth' as parents
        assert parents == {"backend", "backend/auth"}


class TestFilterCases:
    """Test specific filter → expected included modules mappings."""

    def test_filter_backend_auth(self):
        """Filter ['backend/auth'] should include backend, backend/auth, and children."""
        filter_modules = ["backend/auth"]
        expected_included = [
            "backend",  # parent
            "backend/auth",  # exact match
            "backend/auth/login",  # child
            "backend/auth/register",  # child
        ]
        expected_excluded = [
            "backend/api",
            "backend/api/handlers",
            "utils",
            "utils/validation",
            "core",
            "core/db",
            "core/db/models",
            "core/db/migrations",
        ]

        for module in expected_included:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is True, f"Expected {module} to be included"

        for module in expected_excluded:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is False, f"Expected {module} to be excluded"

    def test_filter_core_db_models(self):
        """Filter ['core/db/models'] should include core, core/db, core/db/models."""
        filter_modules = ["core/db/models"]
        expected_included = [
            "core",  # grandparent
            "core/db",  # parent
            "core/db/models",  # exact match
        ]
        expected_excluded = [
            "core/db/migrations",  # sibling
            "backend",
            "utils",
        ]

        for module in expected_included:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is True, f"Expected {module} to be included"

        for module in expected_excluded:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is False, f"Expected {module} to be excluded"

    def test_filter_multiple_modules(self):
        """Filter ['utils', 'backend/api'] should include utils tree and backend/api tree."""
        filter_modules = ["utils", "backend/api"]
        expected_included = [
            "utils",
            "utils/validation",
            "backend",  # parent of backend/api
            "backend/api",
            "backend/api/handlers",
        ]
        expected_excluded = [
            "backend/auth",  # sibling tree
            "backend/auth/login",
            "core",
            "core/db",
        ]

        for module in expected_included:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is True, f"Expected {module} to be included"

        for module in expected_excluded:
            result, _ = should_process_module(module, filter_modules, ALL_MODULE_KEYS)
            assert result is False, f"Expected {module} to be excluded"


class TestEdgeCases:
    """Test edge cases for module filtering."""

    def test_empty_module_key(self):
        """Test empty module key (root level)."""
        result, reason = should_process_module("", ["backend"], ALL_MODULE_KEYS)
        # Empty string won't match any pattern with "/" prefix checks
        assert result is False

    def test_single_component_module(self):
        """Test single component modules (top level)."""
        result, reason = should_process_module("backend", ["backend"], ALL_MODULE_KEYS)
        assert result is True
        assert "exact match" in reason

    def test_overlapping_filters(self):
        """Test overlapping filters don't cause issues."""
        # Both 'backend' and 'backend/auth' in filter - should work fine
        filter_modules = ["backend", "backend/auth"]

        result, reason = should_process_module(
            "backend/auth/login", filter_modules, ALL_MODULE_KEYS
        )
        assert result is True

    def test_module_not_in_tree_still_checked(self):
        """Test that module not in tree is still checked against filter."""
        # all_module_keys is just for reference, shouldn't affect matching logic
        result, reason = should_process_module(
            "nonexistent/module", ["nonexistent/module"], ALL_MODULE_KEYS
        )
        assert result is True
        assert "exact match" in reason

    def test_filter_with_trailing_slash(self):
        """Test filter patterns should NOT have trailing slash."""
        # The function expects clean paths without trailing slashes
        # A filter "backend/" would NOT match "backend" exactly
        result, reason = should_process_module(
            "backend", ["backend/"], ALL_MODULE_KEYS
        )
        # "backend" != "backend/" and doesn't start with "backend//"
        # But "backend/".startswith("backend/") is True, so it's a parent match
        assert result is True
        assert "parent of" in reason
