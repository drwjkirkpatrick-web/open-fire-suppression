"""Tests for BOT-002 — HSM Bridge."""
from pathlib import Path

import pytest

from fire_suppression.diagnostics.hsm_bridge import HSMBridge, HSMKey, PCRMeasurement


class TestHSMBridge:
    def test_init_mock(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        health = hsm.health_check()
        assert health["mock"] is True
        assert health["device"] == "mock"
        assert health["healthy"] is True

    def test_pcr_extend_and_read(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        old = hsm.pcr_read(0)
        hsm.pcr_extend(0, b"measurement-001")
        new = hsm.pcr_read(0)
        assert new != old
        assert len(new) == 32

    def test_pcr_extend_invalid_index(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        with pytest.raises(ValueError):
            hsm.pcr_extend(99, b"bad")

    def test_pcr_quote(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        hsm.pcr_extend(0, b"boot-001")
        quote = hsm.pcr_quote()
        assert "quote" in quote
        assert 0 in quote["quote"]  # dict key, not string
        assert quote["mock"] is True

    def test_generate_key(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        key = hsm.generate_key("ed25519")
        assert key.key_type == "ed25519"
        assert key.public_key is not None
        assert len(key.public_key) == 32

    def test_sign_and_verify(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        sig = hsm.sign_payload(b"fire-event")
        assert len(sig) == 32
        assert hsm.verify_signature(b"fire-event", sig) is True
        assert hsm.verify_signature(b"tampered", sig) is False

    def test_feature_overview(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        ov = hsm.get_feature_overview()
        assert ov["feature_id"] == "BOT-002"
        assert "tpm2" in ov["supports"]

    def test_to_dict(self, tmp_path: Path) -> None:
        hsm = HSMBridge(mock=True, data_dir=tmp_path)
        d = hsm.to_dict()
        assert "healthy" in d
        assert "pcr_values" in d
