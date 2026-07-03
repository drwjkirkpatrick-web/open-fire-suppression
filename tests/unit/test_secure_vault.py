"""Tests for Secure Config Vault (SEC-004).

# C001 — Config load with transparent decryption
# C002 — Config save with transparent encryption
# C003 — Key derivation and mock mode
# C004 — Backup and restore
"""
from pathlib import Path

import pytest
import yaml

from fire_suppression.config.secure_vault import (
    SecureConfigVault,
    _vault_msg,
)


class TestVaultMessages:
    """Bilingual message helpers."""

    def test_english_default(self) -> None:
        msg = _vault_msg("vault_init", source="mock")
        assert "Secure vault initialised" in msg

    def test_swahili(self) -> None:
        msg = _vault_msg("vault_init", lang="sw", source="mock")
        assert "Vault salama" in msg


class TestSecureConfigVault:
    """Core vault functionality."""

    def setup_method(self) -> None:
        self.data_dir = Path("/tmp") / "fire_vault_test"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self) -> None:
        # Clean up test artefacts
        import shutil

        if self.data_dir.exists():
            shutil.rmtree(self.data_dir)

    def _make_vault(self, mock: bool = True) -> SecureConfigVault:
        return SecureConfigVault(data_dir=self.data_dir, mock=mock)

    def _write_config(self, path: Path, data: dict) -> None:
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

    # ── C001 / C002 ──

    def test_roundtrip_encryption(self, tmp_path: Path) -> None:
        """Sensitive values survive encrypt->decrypt roundtrip."""
        cfg_path = tmp_path / "config.yaml"
        self._write_config(
            cfg_path, {"api": {"jwt_secret": "my-secret-123"}}
        )

        vault = self._make_vault()
        vault.sensitive_paths.add("api.jwt_secret")
        vault.load_config(cfg_path)
        vault.save_config()

        # Re-load with fresh vault instance
        vault2 = self._make_vault()
        vault2.sensitive_paths.add("api.jwt_secret")
        loaded = vault2.load_config(cfg_path)

        assert loaded["api"]["jwt_secret"] == "my-secret-123"
        assert vault2.get_sensitive("api.jwt_secret") == "my-secret-123"

    def test_plaintext_fields_untouched(self, tmp_path: Path) -> None:
        """Non-sensitive fields stay readable in YAML."""
        cfg_path = tmp_path / "config.yaml"
        self._write_config(
            cfg_path,
            {"system": {"name": "fire-node-1"}, "api": {"port": 8080}},
        )

        vault = self._make_vault()
        vault.load_config(cfg_path)
        vault.save_config()

        raw = cfg_path.read_text(encoding="utf-8")
        assert "fire-node-1" in raw
        assert "VAULT:" not in raw

    def test_set_sensitive_and_save(self, tmp_path: Path) -> None:
        """set_sensitive injects value and encrypts on save."""
        cfg_path = tmp_path / "config.yaml"
        self._write_config(cfg_path, {"twilio": {"account_sid": ""}})

        vault = self._make_vault()
        vault.sensitive_paths.add("twilio.account_sid")
        vault.load_config(cfg_path)
        vault.set_sensitive("twilio.account_sid", "ACxxxxxxxx")
        vault.save_config()

        vault2 = self._make_vault()
        vault2.sensitive_paths.add("twilio.account_sid")
        loaded = vault2.load_config(cfg_path)
        assert loaded["twilio"]["account_sid"] == "ACxxxxxxxx"

    def test_is_sensitive(self) -> None:
        vault = self._make_vault()
        assert vault.is_sensitive("api.jwt_secret")
        assert not vault.is_sensitive("system.name")

    # ── C003 ──

    def test_mock_mode_deterministic_key(self) -> None:
        """Mock mode derives same key every time (reproducible tests)."""
        v1 = self._make_vault(mock=True)
        v2 = self._make_vault(mock=True)
        assert v1._key == v2._key

    def test_health_check(self) -> None:
        vault = self._make_vault(mock=True)
        health = vault.health_check()
        assert health["vault_ready"] is True
        assert health["key_source"] == "mock"
        assert health["cipher"] == "AES-256-GCM"

    def test_feature_overview(self) -> None:
        vault = self._make_vault(mock=True)
        overview = vault.get_feature_overview()
        assert overview["feature_id"] == "SEC-004"
        assert "encrypt" in overview["supports"]

    # ── C004 ──

    def test_backup_created_on_save(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.yaml"
        self._write_config(cfg_path, {"a": 1})

        vault = self._make_vault()
        vault.load_config(cfg_path)
        vault.save_config()

        backups = vault.list_backups()
        assert len(backups) == 1
        assert backups[0]["original"] == str(cfg_path)
        assert Path(backups[0]["backup"]).exists()

    def test_restore_backup(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.yaml"
        self._write_config(cfg_path, {"version": 1})

        vault = self._make_vault()
        vault.load_config(cfg_path)
        vault.save_config()

        # Mutate original
        cfg_path.write_text("version: 2\n", encoding="utf-8")

        # Restore
        backups = vault.list_backups()
        ts = int(backups[0]["timestamp"])
        ok = vault.restore_backup(ts)
        assert ok is True
        restored = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert restored["version"] == 1

    def test_tamper_detection(self, tmp_path: Path) -> None:
        """Corrupted VAULT payload triggers tamper detection."""
        cfg_path = tmp_path / "config.yaml"
        self._write_config(
            cfg_path, {"api": {"jwt_secret": "secret"}}
        )

        vault = self._make_vault()
        vault.sensitive_paths.add("api.jwt_secret")
        vault.load_config(cfg_path)
        vault.save_config()

        # Corrupt the ciphertext in the saved file
        raw = cfg_path.read_text(encoding="utf-8")
        # Locate the VAULT: payload and flip last hex digit of ciphertext
        prefix, payload = raw.split("VAULT:", 1)
        ct_hex, tag_hex, nonce_hex = payload.strip().split(":")
        ct_hex = ct_hex[:-1] + ("0" if ct_hex[-1] != "0" else "1")
        corrupted = f"{prefix}VAULT:{ct_hex}:{tag_hex}:{nonce_hex}\n"
        cfg_path.write_text(corrupted, encoding="utf-8")

        vault2 = self._make_vault()
        vault2.sensitive_paths.add("api.jwt_secret")
        loaded = vault2.load_config(cfg_path)
        assert "TAMPERED" in loaded["api"]["jwt_secret"]
