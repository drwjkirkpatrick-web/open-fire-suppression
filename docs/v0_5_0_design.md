# v0.5.0 — Anti-Tamper USB Updates + Pi 5 Optimized Blockchain + Inspector Data Package

## Design Document

---

## 1. Anti-Tamper USB Update Agent

**Module:** `src/fire_suppression/diagnostics/usb_update_agent.py`

### Threat Model
- Malicious actor inserts USB with forged "update"
- Insider replaces firmware with compromised version
- Update package modified in transit
- Update applied without authorization
- Previous version not recoverable after bad update

### Security Features
| Feature | Implementation |
|---------|---------------|
| Ed25519 code signing | 32-byte public key baked into device |
| SHA-256 content hash | Verify package integrity before install |
| Atomic updates | Write to `.update-staging/`, verify, atomic rename |
| Rollback | Keep last 3 versions in `.versions/` with chain hashes |
| Update audit trail | Every update logged to blockchain with prev_version_hash |
| Unauthorized USB detection | Alert when untrusted USB inserted |
| Config hash verification | Verify config.yaml hasn't been tampered post-update |
| Hardware-backed key (optional) | TPM 2.0 or ATECC608B secure element support |

### USB Update Package Format
```
update-package/
├── manifest.json       # version, timestamp, target device ID, component list
├── signature.ed25519    # Ed25519 signature of manifest + all files
├── contents.sha256      # Per-file SHA-256 hashes
├── firmware/
│   ├── *.py            # Updated source files
│   └── ...
└── config.patch        # Optional config changes (signed separately)
```

---

## 2. Pi 5 Optimized Blockchain

**Module:** `src/fire_suppression/telemetry/blockchain_audit.py` (enhanced)

### Current Problem
- JSON in-memory chain: O(n) parse for every append
- Full chain loaded into RAM (8GB Pi 5 is fine now, but won't scale)
- Merkle tree recomputed from scratch every time

### Pi 5 Optimizations

| Resource | Constraint | Strategy |
|----------|-----------|----------|
| RAM (8GB) | Don't waste it | Append-only flat file, mmap for reads |
| Storage (256GB M.2) | Plenty for years | ~112 bytes/block, ~4MB/year at 1 event/sec |
| CPU (4-core ARM Cortex-A76) | Lightweight crypto | Ed25519 verification in ~1ms, SHA-256 in hardware |
| Power | Always-on | Periodic batch Merkle computation during idle |

### Storage Format
```
Block binary format (112 bytes):
  index:       uint64   (8 bytes)
  timestamp:   uint64   (8 bytes)  -- seconds since epoch
  prev_hash:   bytes32  (32 bytes) -- SHA-256
  data_hash:   bytes32  (32 bytes) -- SHA-256 of event data JSON
  event_hash:  bytes32  (32 bytes) -- SHA-256 of complete block
```

### What Gets Encoded
Priority 1 (always):
- Fire detection events
- Suppression activations
- System configuration changes
- USB update installations
- Compliance check results
- Owner maintenance alerts sent

Priority 2 (when available):
- Sensor calibration events
- NFPA inspection records
- USB export packages created
- Tamper detection alerts
- Resilience mode changes

Priority 3 (summary only to save space):
- Periodic sensor readings (store hash of batch, not each)
- Telemetry heartbeats (Merkle root of batch)

---

## 3. Anti-Tamper Records in USB Legal Export

**Module:** `src/fire_suppression/telemetry/usb_export.py` (enhanced)

### New Export Sections
| Section | Content |
|---------|---------|
| `tamper_log/` | All tamper detection events with blockchain proofs |
| `update_history/` | Version history, signatures, rollback info |
| `blockchain/` | Full chain or pruned chain with Merkle root |
| `integrity_report/` | File-by-file integrity check of entire system |
| `sensor_calibration/` | Calibration history with pre/post drift measurements |

### Inspector Verification
1. Export includes `verify.sh` script
2. Inspector runs: `./verify.sh` → checks all signatures, hashes, blockchain
3. Output: PASS / FAIL with specific tampered files identified
4. Includes `README_INSPECTOR.md` explaining what each file means

---

## 4. Additional Modules for v0.5.0

### SEC-001: File Integrity Monitor (FIM)
- Continuous SHA-256 monitoring of all Python source files
- Detects unauthorized modifications in real-time
- Alerts + blockchain log on tamper detection

### SEC-002: Hardware Security Module Bridge
- TPM 2.0 or ATECC608B support for key storage
- Private keys never leave secure element
- PCR (Platform Configuration Register) measurements

### SEC-003: Intrusion Detection System
- Monitor for unexpected USB insertions
- Detect unusual process spawning
- Alert on network anomalies

### SEC-004: Secure Config Vault
- Encrypt sensitive config values at rest
- Key derivation from TPM or hardware UID
- Automatic re-encryption on config changes

---

## 5. Wire-Up Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USB Update Agent                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Ed25519      │  │ Atomic       │  │ Rollback     │       │
│  │ Verify       │→ │ Staging      │→ │ Manager      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│           │                                      │           │
│           └──────────────────┬───────────────────┘           │
│                              ▼                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Blockchain Audit Log                        │ │
│  │  update_installed | prev_hash | new_hash | signer        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  USB Legal Export Module                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Blockchain   │  │ Tamper       │  │ Inspector    │     │
│  │ Verification │  │ Log Export   │  │ README +     │     │
│  │ Data         │  │              │  │ verify.sh    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Compliance Impact

| NFPA / Standard | How We Address It |
|-----------------|-------------------|
| NFPA 72 §14.4 | System documentation includes blockchain-backed change log |
| NFPA 72 §14.6 | Software changes logged with cryptographic proof |
| UL 864 | Software-controlled components have verified update mechanism |
| ISO 27001 | Tamper detection and integrity monitoring for audit trails |
| NIST SP 800-53 AU-6 | Automated audit review with anomaly detection |

---

## 7. Pi 5 Performance Budget

| Operation | Time | Memory |
|-----------|------|--------|
| SHA-256 hash (512 bytes) | ~2 µs | 0 |
| Ed25519 verify | ~1 ms | ~4 KB |
| Merkle root (10k blocks) | ~5 ms | ~256 KB |
| Flat file append | ~1 ms | 0 |
| Blockchain verify (10k blocks) | ~20 ms | ~1 MB |
| Full USB export (1GB data) | ~30 s | ~50 MB |

All operations well within Pi 5 capabilities.
