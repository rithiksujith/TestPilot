"""
Tests for backend.discovery.discover_source_files.

All tests use pytest's built-in ``tmp_path`` fixture so they are fully
isolated and leave no files on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.discovery import discover_source_files

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path: Path, content: str = "") -> Path:
    """Create *path* (and any parent directories) with the given content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ===========================================================================
# Basic discovery
# ===========================================================================

class TestDiscoverSourceFiles:
    def test_returns_list(self, tmp_path):
        _touch(tmp_path / "module.py")
        result = discover_source_files(tmp_path)
        assert isinstance(result, list)

    def test_finds_single_source_file(self, tmp_path):
        src = _touch(tmp_path / "app.py")
        result = discover_source_files(tmp_path)
        assert src in result

    def test_finds_multiple_source_files(self, tmp_path):
        a = _touch(tmp_path / "alpha.py")
        b = _touch(tmp_path / "beta.py")
        result = discover_source_files(tmp_path)
        assert a in result
        assert b in result

    def test_result_is_sorted(self, tmp_path):
        _touch(tmp_path / "zebra.py")
        _touch(tmp_path / "apple.py")
        _touch(tmp_path / "mango.py")
        result = discover_source_files(tmp_path)
        assert result == sorted(result)

    def test_returns_absolute_paths(self, tmp_path):
        _touch(tmp_path / "module.py")
        result = discover_source_files(tmp_path)
        for p in result:
            assert p.is_absolute()

    def test_empty_directory_returns_empty_list(self, tmp_path):
        result = discover_source_files(tmp_path)
        assert result == []

    def test_directory_with_only_test_files_returns_empty_list(self, tmp_path):
        _touch(tmp_path / "test_app.py")
        _touch(tmp_path / "app_test.py")
        result = discover_source_files(tmp_path)
        assert result == []


# ===========================================================================
# Test-file exclusion
# ===========================================================================

class TestTestFileExclusion:
    def test_excludes_test_prefix_files(self, tmp_path):
        _touch(tmp_path / "test_module.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_excludes_test_suffix_files(self, tmp_path):
        _touch(tmp_path / "module_test.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_does_not_exclude_files_containing_test_mid_name(self, tmp_path):
        # "mytest_helper.py" does not start with "test_" — should be included.
        src = _touch(tmp_path / "mytest_helper.py")
        result = discover_source_files(tmp_path)
        assert src in result

    def test_excludes_test_prefix_in_subdirectory(self, tmp_path):
        _touch(tmp_path / "sub" / "test_utils.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_excludes_test_suffix_in_subdirectory(self, tmp_path):
        _touch(tmp_path / "sub" / "utils_test.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_source_and_test_files_mixed(self, tmp_path):
        src = _touch(tmp_path / "logic.py")
        _touch(tmp_path / "test_logic.py")
        result = discover_source_files(tmp_path)
        assert result == [src]


# ===========================================================================
# __pycache__ exclusion
# ===========================================================================

class TestPycacheExclusion:
    def test_excludes_files_in_pycache(self, tmp_path):
        _touch(tmp_path / "__pycache__" / "module.cpython-311.pyc")
        # Also create a .py inside __pycache__ (edge case — shouldn't happen
        # in practice but the rule must still exclude it).
        _touch(tmp_path / "__pycache__" / "module.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_excludes_nested_pycache(self, tmp_path):
        _touch(tmp_path / "pkg" / "__pycache__" / "cached.py")
        result = discover_source_files(tmp_path)
        assert result == []

    def test_pycache_sibling_source_is_included(self, tmp_path):
        src = _touch(tmp_path / "pkg" / "module.py")
        _touch(tmp_path / "pkg" / "__pycache__" / "module.py")
        result = discover_source_files(tmp_path)
        assert result == [src]


# ===========================================================================
# Recursive discovery
# ===========================================================================

class TestRecursiveDiscovery:
    def test_finds_files_in_subdirectory(self, tmp_path):
        src = _touch(tmp_path / "src" / "app" / "logic.py")
        result = discover_source_files(tmp_path)
        assert src in result

    def test_finds_files_at_multiple_depths(self, tmp_path):
        top = _touch(tmp_path / "top.py")
        mid = _touch(tmp_path / "pkg" / "mid.py")
        deep = _touch(tmp_path / "pkg" / "sub" / "deep.py")
        result = discover_source_files(tmp_path)
        assert top in result
        assert mid in result
        assert deep in result


# ===========================================================================
# Real demo project
# ===========================================================================

class TestWithBankAccountDemo:
    """Verify that discover_source_files works correctly on the real demo
    project, which is the canonical integration fixture for Phase 2.
    """

    DEMO_DIR = Path("demo_projects/bank_account")

    def test_finds_bank_account_source(self):
        results = discover_source_files(self.DEMO_DIR)
        names = [p.name for p in results]
        assert "bank_account.py" in names

    def test_excludes_test_bank_account(self):
        results = discover_source_files(self.DEMO_DIR)
        names = [p.name for p in results]
        assert "test_bank_account.py" not in names

    def test_returns_at_least_one_file(self):
        results = discover_source_files(self.DEMO_DIR)
        assert len(results) >= 1


# ===========================================================================
# Error handling
# ===========================================================================

class TestErrorHandling:
    def test_raises_for_nonexistent_directory(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(NotADirectoryError):
            discover_source_files(missing)

    def test_raises_for_file_path(self, tmp_path):
        f = _touch(tmp_path / "file.py")
        with pytest.raises(NotADirectoryError):
            discover_source_files(f)

    def test_accepts_string_path(self, tmp_path):
        _touch(tmp_path / "module.py")
        # Should not raise — string input must be accepted.
        result = discover_source_files(str(tmp_path))
        assert len(result) == 1
