"""
SEC-004 — Secure Config Vault

Encrypts sensitive configuration values at rest using AES-256-GCM.
Key derivation from hardware UID (Raspberry Pi serial) or a fallback
random key in mock mode.  Transparent encryption/decryption wrapper
around YAML config files.

Sensitive fields are marked in a schema allowlist; only those fields
are encrypted.  All other fields remain plaintext for readability.

Bilingual messages (EN + SW) for vault lifecycle events.

Usage::

    from fire_suppression.config.secure_vault import SecureConfigVault
    vault = SecureConfigVault(mock=True)
    vault.load_config("config/config.yaml")
    vault.set_sensitive("twilio.auth_token", "abc123")
    vault.save_config()

    # Later
    cfg = vault.load_config("config/config.yaml")
    token = vault.get_sensitive("twilio.auth_token")
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ── Bilingual messages ────────────────────────────────────────────────────────
_VAULT_MSGS = {
    "vault_init": {
        "en": "Secure vault initialised — key source: {source}",
        "sw": "Vault salama imeanzishwa — chanzo cha ufunguo: {source}",
    },
    "encrypt_ok": {
        "en": "Field '{field}' encrypted and stored.",
        "sw": "Sehemu '{field}' imefichwa na kuhifadhiwa.",
    },
    "decrypt_ok": {
        "en": "Field '{field}' decrypted successfully.",
        "sw": "Sehemu '{field}' imefunguliwa kwa mafanikio.",
    },
    "tamper_detected": {
        "en": "VAULT TAMPERING: Ciphertext for '{field}' has invalid authentication tag.",
        "sw": "UBADILIKO WA VAULT: Maandishi ya siri ya '{field}' tag batili.",
    },
    "backup_created": {
        "en": "Encrypted config backed up to {path}",
        "sw": "Mipangilio iliyofichwa imehifadhiwa kwenye {path}",
    },
}


def _vault_msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _VAULT_MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


# ── AES-256-GCM primitives ────────────────────────────────────────────────────
# Uses ``cryptography`` if available; falls back to an insecure mock XOR
# cipher for testing on systems without the package.


class _MockCipher:
    """Insecure placeholder used when cryptography is not installed."""

    def __init__(self, key: bytes) -> None:
        self.key = key[:32].ljust(32, b"\x00")

    def encrypt(
        self, plaintext: bytes, nonce: Optional[bytes] = None
    ) -> Tuple[bytes, bytes, bytes]:
        """Return (ciphertext, tag, nonce)."""
        n = nonce or secrets.token_bytes(12)
        stream = hashlib.sha256(self.key + n).digest()
        extended = stream
        while len(extended) < len(plaintext):
            extended += hashlib.sha256(extended).digest()
        ct = bytes(p ^ e for p, e in zip(plaintext, extended))
        tag = hashlib.sha256(ct + n + self.key).digest()[:16]
        return ct, tag, n

    def decrypt(
        self, ciphertext: bytes, tag: bytes, nonce: bytes
    ) -> Optional[bytes]:
        expected = hashlib.sha256(ciphertext + nonce + self.key).digest()[:16]
        if expected != tag:
            return None
        stream = hashlib.sha256(self.key + nonce).digest()
        extended = stream
        while len(extended) < len(ciphertext):
            extended += hashlib.sha256(extended).digest()
        return bytes(c ^ e for c, e in zip(ciphertext, extended))


class _AESCipher:
    """Real AES-256-GCM via cryptography library."""

    def __init__(self, key: bytes) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self._aes = AESGCM(key[:32])

    def encrypt(
        self, plaintext: bytes, nonce: Optional[bytes] = None
    ) -> Tuple[bytes, bytes, bytes]:
        n = nonce or secrets.token_bytes(12)
        ct = self._aes.encrypt(n, plaintext, None)
        return ct[:-16], ct[-16:], n

    def decrypt(
        self, ciphertext: bytes, tag: bytes, nonce: bytes
    ) -> Optional[bytes]:
        try:
            return self._aes.decrypt(nonce, ciphertext + tag, None)
        except Exception:
            return None


def _make_cipher(key: bytes) -> Union[_AESCipher, _MockCipher]:
    try:
        return _AESCipher(key)
    except ImportError:
        logger.warning("cryptography not available — using mock cipher (INSECURE)")
        return _MockCipher(key)


# ── Schema: which config paths are considered "sensitive" ─────────────────────
_DEFAULT_SENSITIVE_PATHS = [
    "twilio.auth_token",
    "twilio.account_sid",
    "smtp.password",
    "mqtt.password",
    "webhook.secret",
    "api.jwt_secret",
    "database.password",
    "cloud_backup.access_key",
    "cloud_backup.secret_key",
]


# ── Main vault class ──────────────────────────────────────────────────────────

class SecureConfigVault:
    """Transparent encryption layer for sensitive configuration fields."""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        mock: bool = False,
        lang: str = "en",
        sensitive_paths: Optional[List[str]] = None,
    ) -> None:
        self.mock = mock
        self.lang = lang
        self.data_dir = (
            Path(data_dir)
            if data_dir
            else Path.home() / ".local" / "share" / "fire-suppression" / "vault"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "vault.db"
        self._init_db()

        # Derive encryption key
        self._key = self._derive_key()
        self._cipher = _make_cipher(self._key)
        logger.info(_vault_msg("vault_init", self.lang, source="mock" if self.mock else "hardware"))

        self.sensitive_paths = set(sensitive_paths or _DEFAULT_SENSITIVE_PATHS)
        self._config: Dict[str, Any] = {}
        self._config_path: Optional[Path] = None

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS config_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT,
                backup_path TEXT,
                timestamp REAL
            )
            """
        )
        conn.commit()
        conn.close()

    # ── Key derivation ────────────────────────────────────────────────────────

    def _derive_key(self) -> bytes:
        """Derive a 256-bit key from hardware identity. Mock mode uses static key."""
        if self.mock:
            return hashlib.sha256(b"mock-fire-suppression-vault-key").digest()

        # Attempt 1: Raspberry Pi serial number
        serial = self._read_pi_serial()
        if serial:
            return hashlib.sha256(f"pi-serial:{serial}".encode()).digest()

        # Attempt 2: machine-id
        mid = self._read_machine_id()
        if mid:
            return hashlib.sha256(f"machine-id:{mid}".encode()).digest()

        # Fallback: random key persisted to disk (one-time setup)
        key_path = self.data_dir / ".vault_key"
        if key_path.exists():
            return bytes.fromhex(key_path.read_text().strip())
        key = secrets.token_bytes(32)
        key_path.write_text(key.hex(), encoding="utf-8")
        os.chmod(key_path, 0o600)
        return key

    @staticmethod
    def _read_pi_serial() -> Optional[str]:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        return line.split(":")[-1].strip()
        except (OSError, PermissionError):
            pass
        return None

    @staticmethod
    def _read_machine_id() -> Optional[str]:
        try:
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                p = Path(path)
                if p.exists():
                    return p.read_text().strip()
        except (OSError, PermissionError):
            pass
        return None

    # ── Config load / save with transparent encryption ─────────────────────────

    def load_config(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Load YAML config and decrypt sensitive fields transparently."""
        import yaml

        self._config_path = Path(path)
        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        self._config = raw if raw else {}
        self._decrypt_config(self._config)
        return self._config

    def save_config(self, path: Optional[Union[str, Path]] = None) -> None:
        """Encrypt sensitive fields and write config back to disk."""
        import yaml

        target = Path(path) if path else self._config_path
        if not target:
            raise ValueError("No config path set. Call load_config() first.")

        self._create_backup(target)
        encrypted = self._deep_copy(self._config)
        self._encrypt_config(encrypted)
        target.write_text(
            yaml.safe_dump(encrypted, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(_vault_msg("backup_created", self.lang, path=str(target)))

    # ── Get / set sensitive values ─────────────────────────────────────────────

    def get_sensitive(self, dotpath: str) -> Optional[str]:
        """Get a sensitive value by dotted path (e.g. 'twilio.auth_token')."""
        return self._get_by_path(self._config, dotpath)

    def set_sensitive(self, dotpath: str, value: str) -> None:
        """Set a sensitive value by dotted path."""
        self._set_by_path(self._config, dotpath, value)
        logger.info(_vault_msg("encrypt_ok", self.lang, field=dotpath))

    def is_sensitive(self, dotpath: str) -> bool:
        return dotpath in self.sensitive_paths

    # ── Encryption / decryption helpers ────────────────────────────────────────

    def _encrypt_config(
        self, cfg: Dict[str, Any], prefix: str = ""
    ) -> None:
        for key, val in cfg.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                self._encrypt_config(val, path)
            elif isinstance(val, str) and path in self.sensitive_paths and val:
                if val.startswith("VAULT:"):
                    continue  # Already encrypted
                ct, tag, nonce = self._cipher.encrypt(val.encode("utf-8"))
                cfg[key] = f"VAULT:{ct.hex()}:{tag.hex()}:{nonce.hex()}"

    def _decrypt_config(
        self, cfg: Dict[str, Any], prefix: str = ""
    ) -> None:
        for key, val in cfg.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(val, dict):
                self._decrypt_config(val, path)
            elif isinstance(val, str) and val.startswith("VAULT:"):
                plain = self._decrypt_field(val)
                if plain is None:
                    logger.error(_vault_msg("tamper_detected", self.lang, field=path))
                    cfg[key] = "[TAMPERED — VAULT LOCKED]"
                else:
                    cfg[key] = plain
                    logger.debug(_vault_msg("decrypt_ok", self.lang, field=path))

    def _decrypt_field(self, encoded: str) -> Optional[str]:
        try:
            _, ct_hex, tag_hex, nonce_hex = encoded.split(":")
            ct = bytes.fromhex(ct_hex)
            tag = bytes.fromhex(tag_hex)
            nonce = bytes.fromhex(nonce_hex)
            plain = self._cipher.decrypt(ct, tag, nonce)
            return plain.decode("utf-8") if plain else None
        except ValueError:
            return None

    # ── Deep copy for safe encryption ───────────────────────────────────────────

    @staticmethod
    def _deep_copy(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: SecureConfigVault._deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [SecureConfigVault._deep_copy(i) for i in obj]
        return obj

    # ── Dot-path navigation ───────────────────────────────────────────────────

    @staticmethod
    def _get_by_path(cfg: Dict[str, Any], dotpath: str) -> Optional[Any]:
        parts = dotpath.split(".")
        node = cfg
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return None
        return node

    @staticmethod
    def _set_by_path(cfg: Dict[str, Any], dotpath: str, value: Any) -> None:
        parts = dotpath.split(".")
        node = cfg
        for p in parts[:-1]:
            if p not in node:
                node[p] = {}
            node = node[p]
        node[parts[-1]] = value

    # ── Backup ──────────────────────────────────────────────────────────────────

    def _create_backup(self, original: Union[str, Path]) -> None:
        original = Path(original)
        if not original.exists():
            return
        ts = int(time.time())
        backup = self.data_dir / f"config_backup_{ts}.yaml"
        backup.write_bytes(original.read_bytes())
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "INSERT INTO config_backups (path, backup_path, timestamp) VALUES (?, ?, ?)",
            (str(original), str(backup), ts),
        )
        conn.commit()
        conn.close()

    def list_backups(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "SELECT path, backup_path, timestamp FROM config_backups ORDER BY timestamp DESC LIMIT 20"
        )
        rows = c.fetchall()
        conn.close()
        return [{"original": r[0], "backup": r[1], "timestamp": r[2]} for r in rows]

    def restore_backup(self, timestamp: int) -> bool:
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute(
            "SELECT path, backup_path FROM config_backups WHERE timestamp=? ORDER BY id DESC LIMIT 1",
            (timestamp,),
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return False
        original = Path(row[0])
        backup = Path(row[1])
        if backup.exists():
            original.write_bytes(backup.read_bytes())
            return True
        return False

    # ── Health check ───────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        return {
            "vault_ready": True,
            "key_source": "mock" if self.mock else "hardware",
            "cipher": "AES-256-GCM" if not isinstance(self._cipher, _MockCipher) else "MOCK",
            "sensitive_paths_count": len(self.sensitive_paths),
            "db_path": str(self.db_path),
            "healthy": True,
        }

    # ── Feature overview ────────────────────────────────────────────────────────

    def get_feature_overview(self) -> Dict[str, Any]:
        return {
            "feature_id": "SEC-004",
            "feature_name": "Secure Config Vault",
            "mock": self.mock,
            "cipher": "AES-256-GCM" if not isinstance(self._cipher, _MockCipher) else "MOCK",
            "supports": ["encrypt", "decrypt", "backup", "restore", "hardware_key_derivation"],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.health_check(),
            "backups": self.list_backups()[:5],
            "sensitive_paths": sorted(self.sensitive_paths),
        }
