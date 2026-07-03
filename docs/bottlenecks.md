# 10 Critical Bottlenecks & Resilience Analysis

## BOT-001 — Single Sensor Failure Cascade
**Problem**: If MQ-2 burns up or its wiring melts, the detection engine may crash on read(), bringing down the entire polling loop.
**Impact**: System blind to fire during a fire.
**Mitigation**: Wrap every sensor read in try/except, mark failed sensors degraded, continue with remaining sensors.
**Status**: Core already has this; needs enhancement for graceful degradation weights.

## BOT-002 — Detection Engine Freezing
**Problem**: Sensor fusion calculation or Kalman filter inversion could hang if matrix becomes singular.
**Impact**: Detection loop stalls; no new fire states computed.
**Mitigation**: Timeout on detection computation (async with asyncio.wait_for), fallback to simple threshold mode.
**Status**: Needs build.

## BOT-003 — SQLite Database Corruption
**Problem**: Power loss during write can corrupt SQLite WAL, preventing event logging and dashboard queries.
**Impact**: No audit trail; dashboard 500 errors.
**Mitigation**: SQLite PRAGMAs for robustness, backup DB rotation, WAL checkpointing, fallback to JSON file logging.
**Status**: Needs build.

## BOT-004 — Memory Leak on Long Runtime
**Problem**: Python object accumulation (sensor readings, detection results, log buffers) over weeks/months.
**Impact**: OOM killer terminates the process.
**Mitigation**: Periodic memory profiling, bounded queues, explicit `del` on large buffers, memory alert threshold.
**Status**: Needs build.

## BOT-005 — Network Partition during Emergency
**Problem**: WiFi fails during fire (router melts, power cut). SMS/webhook alerts can't send.
**Impact**: Remote notifications lost, but local suppression may still work.
**Mitigation**: Store-and-forward queue with local persistence, retry on reconnect, cellular backup as primary when WiFi fails.
**Status**: Needs build.

## BOT-006 — Cascading Relay Failure
**Problem**: One relay driver fails shorted, drawing excessive current, causing Pi brownout or GPIO damage.
**Impact**: All relays fail, suppression system dead.
**Mitigation**: Per-relay fuse monitoring, current sensing, relay health checks, graceful isolation of failed relays.
**Status**: Needs build.

## BOT-007 — Configuration Corruption on Hot Reload
**Problem**: SIGUSR1 reload while YAML is mid-write results in partial config.
**Impact**: Invalid thresholds, potentially dangerous defaults.
**Mitigation**: Atomic file writes (write to temp, rename), config validation on every reload, fallback to last-known-good.
**Status**: Needs build.

## BOT-008 — Thermal Camera Blind Spot
**Problem**: MLX90640 thermal camera has a narrow FOV (~110°). Fire outside FOV is invisible.
**Impact**: Delayed detection until fire spreads into camera view.
**Mitigation**: Multiple thermal cameras with overlapping coverage, or wide-AMG8833 for peripheral monitoring.
**Status**: Hardware/architecture; documented.

## BOT-009 — Clock Drift / NTP Failure
**Problem**: Raspberry Pi has no RTC. After power loss, timestamps are wrong until NTP syncs.
**Impact**: Event logs have wrong times, audit chain appears suspicious.
**Mitigation**: DS3231 RTC module, NTP sync monitoring, timestamp confidence flagging.
**Status**: Needs build.

## BOT-010 — Python Process Death
**Problem**: The main Python process could segfault, OOM, or be killed.
**Impact**: Entire system offline, no detection, no suppression.
**Mitigation**: systemd service with restart=always, health heartbeat to external watchdog (hardware or systemd), dual-process architecture with primary/backup.
**Status**: Needs build.
