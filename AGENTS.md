# AGENTS.md

# MemoryOps AI - AI Engineering Contract

Version: 0.1

---

# Purpose

This repository is designed to be developed collaboratively by human engineers and AI coding agents.

The goal of this document is to establish engineering expectations before implementation begins.

AI agents should behave like senior software engineers rather than code generators.

Every change should improve the long-term maintainability, reliability, and clarity of the system.

---

# Project Overview

MemoryOps AI is a production-grade memory operating system for AI applications.

The platform manages the complete lifecycle of memory including:

- extraction
- validation
- classification
- storage
- retrieval
- ranking
- governance
- lifecycle management
- evaluation
- observability

Memory is treated as governed system state rather than simple vector storage.

---

# Engineering Philosophy

Always optimize for:

- correctness
- maintainability
- simplicity
- observability
- explainability
- extensibility

Avoid optimizing for:

- unnecessary abstraction
- premature optimization
- unnecessary frameworks
- hidden behavior
- duplicated logic

---

# Repository Source of Truth

Before making any implementation decisions, read these documents in order.

1. Product Blueprint
2. ROADMAP.md
3. Architecture documents
4. ADRs
5. Phase Gates

Implementation must follow documented architecture whenever possible.

---

# Engineering Workflow

Every task should follow this sequence.

Understand

↓

Design

↓

Validate

↓

Implement

↓

Test

↓

Document

↓

Review

Do not skip documentation because implementation appears simple.

---

# Before Starting Any Task

Determine:

- What problem is being solved?
- Which roadmap version does this belong to?
- Does this change affect architecture?
- Does this require a new ADR?
- Which documentation must change?
- Which tests will validate this change?

If these questions cannot be answered, stop and ask for clarification.

---

# Architecture Changes

If a change modifies:

- system boundaries
- storage architecture
- APIs
- data models
- deployment
- retrieval strategy
- evaluation methodology
- governance policies

then:

- explain the reasoning
- compare alternatives
- recommend a solution
- determine whether an ADR is required

Do not silently introduce architectural changes.

---

# Documentation Rules

Documentation is considered part of the implementation.

Whenever behavior changes:

- update documentation
- update architecture if required
- update roadmap if milestones change
- update ADRs when architectural intent changes

Implementation without documentation is incomplete.

---

# Code Quality

Produce code that is:

- modular
- readable
- typed
- documented
- testable
- production-oriented

Avoid unnecessary complexity.

Favor explicit logic over clever implementations.

---

# Testing

Every feature should include an appropriate validation strategy.

Possible validation includes:

- unit tests
- integration tests
- API tests
- evaluation benchmarks
- manual verification

Choose the smallest test capable of proving correctness.

---

# AI-Specific Engineering

When implementing AI capabilities:

Do not assume LLM output is correct.

Separate deterministic logic from probabilistic reasoning.

Make important decisions explainable.

Measure quality whenever possible.

Prefer evaluation over intuition.

---

# Security

Never introduce:

- hardcoded secrets
- exposed credentials
- insecure defaults
- unnecessary permissions

Validate all external input.

Fail safely.

---

# Repository Organization

Applications belong inside:

apps/

Business logic belongs inside:

services/

Infrastructure belongs inside:

infra/

Engineering knowledge belongs inside:

docs/

Tests belong inside:

tests/

Evaluation assets belong inside:

evals/

Do not mix responsibilities.

---

# Communication

Before implementing a major feature:

Summarize:

- problem
- proposed solution
- tradeoffs
- implementation plan

Wait for confirmation if architectural impact is significant.

---

# Definition of Done

A task is complete only when:

- implementation works
- tests pass
- documentation is updated
- architecture remains consistent
- no unnecessary complexity is introduced

---

# Engineering Principle

Write code that another engineer can understand six months from now.

Repository quality is measured by clarity rather than code volume.