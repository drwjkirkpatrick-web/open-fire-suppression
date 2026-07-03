"""Tests for file integrity monitor and Pi-optimized blockchain.

# SEC-001 + MOD-010-OPT Tests
"""
import asyncio
import json
import time

import pytest

from fire_suppression.diagnostics.file_integrity_monitor import (
    FileIntegrityMonitor,
    IntegrityBaseline,
)
from fire_suppression.telemetry.blockchain_audit import (
    AuditBlock,
    BlockchainAudit,
)


class TestAuditBlock:
    def test_binary_roundtrip(self) -> None:
        block = AuditBlock(
            index=1,
            timestamp=int(time.time()),
            previous_hash=b"\x00" * 32,
            data_hash=b"\xab" * 32,
            block_hash=b"\xcd" * 32,
            event_type="TEST",
            event_data={"key": "value"},
        )
        binary = block.to_binary()
        assert len(binary) == 112
        parsed = AuditBlock.from_binary(binary, event_type="TEST", event_data={"key": "value"})
        assert parsed.index == block.index
        assert parsed.timestamp == block.timestamp
        assert parsed.previous_hash == block.previous_hash

    def test_to_dict(self) -> None:
        block = AuditBlock(
            index=0,
            timestamp=1234567890,
            previous_hash=b"\x00" * 32,
            data_hash=b"\xab" * 32,
            block_hash=b"\xcd" * 32,
            event_type="GENESIS",
            event_data={"system": "test"},
        )
        d = block.to_dict()
        assert d["index"] == 0
        assert d["event_type"] == "GENESIS"
        assert "block_hash" in d


class TestBlockchainAudit:
    def test_mock_init(self) -> None:
        audit = BlockchainAudit(mock=True)
        assert audit.get_block_count() >= 1  # genesis
        assert audit.get_latest_hash() != "0" * 64

    def test_add_event(self) -> None:
        audit = BlockchainAudit(mock=True)
        block = audit.add_event("FIRE_DETECTED", {"zone": "kitchen", "confidence": 0.95})
        assert block.index == 1
        assert block.event_type == "FIRE_DETECTED"
        assert block.block_hash is not None

    def test_verify_chain_mock(self) -> None:
        audit = BlockchainAudit(mock=True)
        audit.add_event("EVENT_A", {"data": 1})
        audit.add_event("EVENT_B", {"data": 2})
        result = audit.verify_chain()
        assert result["valid"] is True
        assert result["total_blocks"] == 3  # genesis + 2

    def test_merkle_root(self) -> None:
        audit = BlockchainAudit(mock=True)
        root = audit.get_merkle_root()
        assert len(root) == 64
        assert root != "0" * 64
        # Adding events should change root
        old_root = root
        audit.add_event("NEW_EVENT", {"data": "test"})
        new_root = audit.get_merkle_root()
        assert new_root != old_root

    def test_get_chain_stats(self) -> None:
        audit = BlockchainAudit(mock=True)
        stats = audit.get_chain_stats()
        assert "total_blocks" in stats
        assert "avg_block_size" in stats

    def test_anchor_merkle_root(self) -> None:
        audit = BlockchainAudit(mock=True)
        result = audit.anchor_merkle_root()
        assert result["status"] == "mock_anchored"
        assert "merkle_root" in result
        assert result["total_blocks"] >= 2  # genesis + anchor

    def test_to_dict(self) -> None:
        audit = BlockchainAudit(mock=True)
        d = audit.to_dict()
        assert d["verified"] is True
        assert d["mock"] is True
        assert "latest_hash" in d


class TestFileIntegrityMonitor:
    def test_init(self, tmp_path) -> None:
        fim = FileIntegrityMonitor(project_root=str(tmp_path), mock=True)
        stats = fim.get_stats()
        assert stats["baseline_exists"] is False

    @pytest.mark.asyncio
    async def test_create_baseline(self, tmp_path) -> None:
        # Create some test files
        src_dir = tmp_path / "src" / "fire_suppression"
        src_dir.mkdir(parents=True)
        (src_dir / "test.py").write_text("print('hello')", encoding="utf-8")
        (src_dir / "config.yaml").write_text("test: value", encoding="utf-8")

        fim = FileIntegrityMonitor(
            project_root=str(tmp_path),
            scan_paths=["src/fire_suppression"],
            mock=True,
        )
        baseline = await fim.create_baseline()
        assert isinstance(baseline, IntegrityBaseline)
        assert len(baseline.files) >= 2
        assert "src/fire_suppression/test.py" in baseline.files

    @pytest.mark.asyncio
    async def test_scan_clean(self, tmp_path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("print('hello')", encoding="utf-8")

        fim = FileIntegrityMonitor(project_root=str(tmp_path), scan_paths=["src"], mock=True)
        await fim.create_baseline()
        tampered = await fim.scan()
        assert len(tampered) == 0

    @pytest.mark.asyncio
    async def test_scan_modified(self, tmp_path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        fim = FileIntegrityMonitor(project_root=str(tmp_path), scan_paths=["src"], mock=True)
        await fim.create_baseline()

        # Modify the file
        test_file.write_text("print('modified')", encoding="utf-8")

        tampered = await fim.scan()
        assert len(tampered) == 1
        assert tampered[0]["issue"] == "modified"
        assert tampered[0]["file"] == "src/test.py"

    @pytest.mark.asyncio
    async def test_scan_new_file(self, tmp_path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("print('hello')", encoding="utf-8")

        fim = FileIntegrityMonitor(project_root=str(tmp_path), scan_paths=["src"], mock=True)
        await fim.create_baseline()

        # Add new file
        (src_dir / "new.py").write_text("print('new')", encoding="utf-8")

        tampered = await fim.scan()
        assert len(tampered) == 1
        assert tampered[0]["issue"] == "new_file"

    @pytest.mark.asyncio
    async def test_scan_deleted(self, tmp_path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        fim = FileIntegrityMonitor(project_root=str(tmp_path), scan_paths=["src"], mock=True)
        await fim.create_baseline()

        # Delete file
        test_file.unlink()

        tampered = await fim.scan()
        assert len(tampered) == 1
        assert tampered[0]["issue"] == "deleted"

    def test_excluded_patterns(self, tmp_path) -> None:
        fim = FileIntegrityMonitor(
            project_root=str(tmp_path),
            excluded_patterns=["__pycache__", "*.pyc"],
            mock=True,
        )
        assert fim._is_excluded("src/__pycache__/test.py") is True
        assert fim._is_excluded("src/test.py") is False

    def test_get_stats_no_baseline(self, tmp_path) -> None:
        fim = FileIntegrityMonitor(project_root=str(tmp_path), mock=True)
        stats = fim.get_stats()
        assert stats["baseline_exists"] is False
        assert stats["monitored_files"] == 0

    def test_to_dict(self, tmp_path) -> None:
        fim = FileIntegrityMonitor(project_root=str(tmp_path), mock=True)
        d = fim.to_dict()
        assert "baseline_exists" in d
        assert "scan_paths" in d
