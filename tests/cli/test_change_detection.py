"""
Tests for codewiki.cli.utils.change_detection module.

Covers detect_changed_files() and invalidate_affected_modules() with
various scenarios including base_commit override, missing metadata,
path-based matching, and parent module invalidation.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from codewiki.cli.utils.change_detection import (
    detect_changed_files,
    invalidate_affected_modules,
    _path_matches_changed_files,
    _build_changed_files_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path):
    """Create a temporary output directory with metadata and module tree."""
    metadata = {
        "generation_info": {
            "commit_id": "aaa1111",
            "timestamp": "2026-01-01T00:00:00",
        }
    }
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))

    module_tree = {
        "backend_auth": {
            "components": ["app/Services/Auth/AuthService.php", "app/Models/User.php"],
            "children": {}
        },
        "backend_tracking": {
            "components": ["app/Services/Tracking/TrackingService.php"],
            "children": {
                "tracking_air": {
                    "components": ["app/Services/Tracking/Air/AirTrackingService.php"],
                    "children": {}
                }
            }
        },
    }
    (tmp_path / "module_tree.json").write_text(json.dumps(module_tree))

    # Create .md files to be invalidated
    (tmp_path / "backend_auth.md").write_text("# Auth")
    (tmp_path / "backend_tracking.md").write_text("# Tracking")
    (tmp_path / "tracking_air.md").write_text("# Air Tracking")
    (tmp_path / "overview.md").write_text("# Overview")

    return tmp_path


@pytest.fixture
def mock_repo():
    """Create a mock git.Repo object."""
    repo = MagicMock()
    repo.head.commit.hexsha = "bbb2222"
    return repo


# ---------------------------------------------------------------------------
# detect_changed_files tests
# ---------------------------------------------------------------------------

class TestDetectChangedFiles:

    @patch("codewiki.cli.utils.change_detection.git")
    def test_returns_changed_files_from_metadata(self, mock_git, tmp_output, mock_repo):
        """detect_changed_files() returns list of changed file paths using metadata commit."""
        mock_git.Repo.return_value = mock_repo

        diff_a = MagicMock()
        diff_a.a_path = "app/Services/Auth/AuthService.php"
        diff_a.b_path = "app/Services/Auth/AuthService.php"

        mock_repo.commit.return_value.diff.return_value = [diff_a]

        result = detect_changed_files(Path("/repo"), tmp_output, verbose=True)

        assert result == ["app/Services/Auth/AuthService.php"]
        mock_repo.commit.assert_called_with("aaa1111")

    @patch("codewiki.cli.utils.change_detection.git")
    def test_base_commit_overrides_metadata(self, mock_git, tmp_output, mock_repo):
        """When base_commit is provided, it overrides metadata.json commit_id."""
        mock_git.Repo.return_value = mock_repo

        diff_a = MagicMock()
        diff_a.a_path = "some/file.py"
        diff_a.b_path = "some/file.py"

        mock_repo.commit.return_value.diff.return_value = [diff_a]

        result = detect_changed_files(
            Path("/repo"), tmp_output, verbose=True, base_commit="ccc3333"
        )

        assert result == ["some/file.py"]
        mock_repo.commit.assert_called_with("ccc3333")

    @patch("codewiki.cli.utils.change_detection.git")
    def test_base_commit_works_without_metadata(self, mock_git, tmp_path, mock_repo):
        """base_commit allows detection even when metadata.json doesn't exist."""
        mock_git.Repo.return_value = mock_repo

        diff_a = MagicMock()
        diff_a.a_path = "file.py"
        diff_a.b_path = "file.py"
        mock_repo.commit.return_value.diff.return_value = [diff_a]

        result = detect_changed_files(
            Path("/repo"), tmp_path, base_commit="ccc3333"
        )

        assert result == ["file.py"]

    def test_returns_none_without_metadata_or_base_commit(self, tmp_path):
        """Returns None when no metadata.json and no base_commit."""
        result = detect_changed_files(Path("/repo"), tmp_path)
        assert result is None

    def test_returns_none_with_null_commit_in_metadata(self, tmp_path):
        """Returns None when metadata exists but commit_id is null."""
        metadata = {"generation_info": {"commit_id": None}}
        (tmp_path / "metadata.json").write_text(json.dumps(metadata))

        result = detect_changed_files(Path("/repo"), tmp_path)
        assert result is None

    @patch("codewiki.cli.utils.change_detection.git")
    def test_returns_empty_when_no_changes(self, mock_git, tmp_output, mock_repo):
        """Returns empty list when HEAD matches the base commit."""
        mock_repo.head.commit.hexsha = "aaa1111"  # Same as metadata
        mock_git.Repo.return_value = mock_repo

        result = detect_changed_files(Path("/repo"), tmp_output, verbose=True)

        assert result == []

    @patch("codewiki.cli.utils.change_detection.git")
    def test_returns_none_on_git_error(self, mock_git, tmp_output):
        """Returns None when git operations fail."""
        mock_git.Repo.side_effect = Exception("Not a git repo")

        result = detect_changed_files(Path("/repo"), tmp_output, verbose=True)
        assert result is None

    def test_returns_none_on_corrupt_metadata(self, tmp_path):
        """Returns None when metadata.json is not valid JSON."""
        (tmp_path / "metadata.json").write_text("not json {{{")

        result = detect_changed_files(Path("/repo"), tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# invalidate_affected_modules tests
# ---------------------------------------------------------------------------

class TestInvalidateAffectedModules:

    def test_invalidates_matching_modules(self, tmp_output):
        """Modules with matching changed files are invalidated."""
        changed = ["app/Services/Auth/AuthService.php"]

        result = invalidate_affected_modules(tmp_output, changed, verbose=True)

        assert "backend_auth" in result
        assert "overview" in result
        assert not (tmp_output / "backend_auth.md").exists()
        assert not (tmp_output / "overview.md").exists()
        # Unaffected modules remain
        assert (tmp_output / "backend_tracking.md").exists()

    def test_invalidates_parent_modules(self, tmp_output):
        """Parent modules are invalidated when child module is affected."""
        changed = ["app/Services/Tracking/Air/AirTrackingService.php"]

        result = invalidate_affected_modules(tmp_output, changed, verbose=True)

        assert "tracking_air" in result
        assert "backend_tracking" in result  # parent
        assert "overview" in result

    def test_returns_empty_when_no_module_tree(self, tmp_path):
        """Returns empty list when module_tree.json doesn't exist."""
        result = invalidate_affected_modules(tmp_path, ["some/file.py"])
        assert result == []

    def test_returns_empty_when_no_matches(self, tmp_output):
        """Returns empty list when no changed files match any module components."""
        result = invalidate_affected_modules(
            tmp_output, ["totally/unrelated/file.txt"]
        )
        assert result == []

    def test_handles_corrupt_module_tree(self, tmp_path):
        """Returns empty list when module_tree.json is invalid."""
        (tmp_path / "module_tree.json").write_text("invalid json")
        result = invalidate_affected_modules(tmp_path, ["file.py"])
        assert result == []


# ---------------------------------------------------------------------------
# _path_matches_changed_files tests
# ---------------------------------------------------------------------------

class TestPathMatchesChangedFiles:

    def _idx(self, files):
        """Helper: build index from a set of file paths."""
        return _build_changed_files_index(files)

    def test_exact_match(self):
        assert _path_matches_changed_files(
            "app/Services/Auth.php", self._idx({"app/Services/Auth.php"})
        )

    def test_component_as_filename_in_path(self):
        """Component name (class) matches when it appears as a path segment."""
        assert _path_matches_changed_files(
            "AuthService.php", self._idx({"app/Services/Auth/AuthService.php"})
        )

    def test_no_false_positive_substring(self):
        """'util' should NOT match 'utilities' (substring, not path segment)."""
        assert not _path_matches_changed_files(
            "util", self._idx({"app/utilities/helper.py"})
        )

    def test_no_false_positive_partial_name(self):
        """'User' should NOT match 'UserPreference' (partial name)."""
        assert not _path_matches_changed_files(
            "User", self._idx({"app/Models/UserPreference.php"})
        )

    def test_path_segment_match(self):
        """Changed file that is a proper segment of the component."""
        assert _path_matches_changed_files(
            "app/Services/Auth/AuthService.php",
            self._idx({"app/Services/Auth/AuthService.php"})
        )

    def test_dot_separated_class_name(self):
        """Dot-separated class name matches corresponding file path."""
        assert _path_matches_changed_files(
            "App.Services.Tracking.Sea.Logs.SeaTrackingApiCallsService",
            self._idx({"app/Services/Tracking/Sea/Logs/SeaTrackingApiCallsService.php"})
        )

    def test_dot_separated_class_with_method(self):
        """Dot-separated class.method matches the class file path."""
        assert _path_matches_changed_files(
            "App.Console.Commands.AddIndexesToTenderRequestsRoutes.handle",
            self._idx({"app/Console/Commands/AddIndexesToTenderRequestsRoutes.php"})
        )

    def test_dot_separated_no_false_positive(self):
        """Dot-separated class name should NOT match unrelated file."""
        assert not _path_matches_changed_files(
            "App.Services.Tracking.Sea.Logs.SeaTrackingApiCallsService",
            self._idx({"app/Services/Tracking/Air/AirTrackingService.php"})
        )

    def test_index_precomputation_enables_efficient_lookups(self):
        """Verify index contains expected structures for set-based O(1) lookups."""
        files = {"app/Services/Auth/AuthService.php", "app/Models/User.php"}
        idx = _build_changed_files_index(files)

        assert "app/Services/Auth/AuthService.php" in idx["exact"]
        assert "app/services/auth/authservice" in idx["normalized"]
        assert "authservice" in idx["basenames"]
        assert "services/auth/authservice" in idx["suffixes"]
        assert "auth/authservice" in idx["suffixes"]

    def test_large_changeset_does_not_iterate(self):
        """With many changed files, matching is still O(1) per component via index."""
        # 1000 unrelated files + the one we care about
        files = {f"src/unrelated/module{i}/file{i}.py" for i in range(1000)}
        files.add("app/Services/Auth/AuthService.php")
        idx = self._idx(files)

        # Should match via index lookup, not by iterating 1001 files
        assert _path_matches_changed_files("AuthService", idx)
        assert not _path_matches_changed_files("NonExistent", idx)


# ---------------------------------------------------------------------------
# Atomic write tests for metadata.json (NFR-001)
# ---------------------------------------------------------------------------

class TestAtomicWrite:

    def test_save_json_atomic_produces_valid_file(self, tmp_path):
        """Atomic save_json writes valid JSON file via temp-then-rename."""
        from codewiki.src.utils import file_manager

        filepath = str(tmp_path / "metadata.json")
        data = {"generation_info": {"commit_id": "abc1234"}}

        file_manager.save_json(data, filepath, atomic=True)

        result = json.loads(Path(filepath).read_text())
        assert result == data

    def test_save_json_atomic_no_temp_file_left(self, tmp_path):
        """Atomic save should not leave temporary files behind."""
        from codewiki.src.utils import file_manager

        filepath = str(tmp_path / "metadata.json")
        file_manager.save_json({"key": "value"}, filepath, atomic=True)

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "metadata.json"

    def test_save_json_atomic_overwrites_existing(self, tmp_path):
        """Atomic save overwrites an existing file cleanly."""
        from codewiki.src.utils import file_manager

        filepath = str(tmp_path / "metadata.json")
        file_manager.save_json({"old": True}, filepath, atomic=True)
        file_manager.save_json({"new": True}, filepath, atomic=True)

        result = json.loads(Path(filepath).read_text())
        assert result == {"new": True}

    def test_save_json_non_atomic_still_works(self, tmp_path):
        """Non-atomic (default) save_json still works as before."""
        from codewiki.src.utils import file_manager

        filepath = str(tmp_path / "test.json")
        data = {"hello": "world"}

        file_manager.save_json(data, filepath)

        result = json.loads(Path(filepath).read_text())
        assert result == data
