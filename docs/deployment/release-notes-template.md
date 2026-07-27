# Release Notes & CHANGELOG Template

Use this template to document release history. Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) formats and [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Describe new capabilities, endpoints, or features introduced.
- Example: "Added Postgres connection pool metric monitoring."

### Changed
- Describe modifications to existing functionality.
- Example: "Changed embedding service to use local mock offline fallback."

### Deprecated
- Describe features that will be removed in future versions.
- Example: "Deprecated the legacy memory list API endpoint."

### Removed
- Describe previously deprecated features that have been removed.

### Fixed
- Describe bug fixes or error remediation.
- Example: "Fixed race condition when initiating database connection pools."

### Security
- Describe vulnerability patches or credential handling modifications.

---

## [v1.0.0] - 2026-07-27

### Added
- High-performance vector database persistence via PostgreSQL and `pgvector`.
- Complete memory extraction, validation, compaction, and archiving lifecycle pipeline.
- Observability and tracing span recordings.
- Concurrency validation suite, stress load tests, and failover validation scripts.
- Operational runbooks for pool starvation, backup-restore operations, and production incident response.
- Automated backup, integrity check, and database restoration utilities.
