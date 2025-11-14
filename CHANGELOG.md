# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-11-14

### Added

- Initial MVP release
- MCP-based browser automation via chrome-devtools-mcp
- Search box detection and interaction
- Results extraction with heuristics-based DOM parsing
- Modal/popup handling
- LLM-as-a-judge evaluation system
- Structured scoring rubric (0-5 scale)
- Markdown and HTML report generation
- JSONL audit logs
- CLI interface with argparse
- Nike.com example configuration and queries
- Rate limiting and retry logic
- Deterministic mode with seed support
- Full-page screenshots
- HTML snapshots for traceability
- Configuration system with YAML
- Site-specific config overrides
- Unit tests for core types and config
- Comprehensive documentation

### Features

- **P0 Requirements Met**:
  - ✅ Works with Nike.com and 10 English queries
  - ✅ Opens Chrome via chrome-devtools-mcp (headless by default)
  - ✅ Locates search box, submits queries, waits for results
  - ✅ Extracts top-K results with metadata
  - ✅ Screenshots and HTML snapshots
  - ✅ LLM judge with structured rubric
  - ✅ JSONL audit and Markdown/HTML reports
  - ✅ Deterministic mode with --seed
  - ✅ End-to-end execution without manual intervention

### Known Limitations

- OpenAI only (multi-LLM support planned)
- English only (i18n planned)
- No robots.txt checking yet
- No LLM-generated queries yet (P1 feature)

## [Unreleased]

### Planned Features

- Multi-LLM support (Anthropic, Gemini)
- LLM-generated queries from site content
- Multi-language support
- Cross-model reliability experiments
- Robots.txt compliance
- Enhanced selector auto-detection
- Improved error handling and recovery
- Performance optimizations
