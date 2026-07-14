import pytest
import asyncio
from app.domain import CandidateMemory, PolicyDecision, Sensitivity, MemoryType
from app.policy import PolicyBroker

def test_secret_blocking_openai_key():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Remember that my API key is sk-test-123456789abcdefghij.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
        assert "secret or credential pattern" in result.reason
        assert "sk-test" not in result.reason
    asyncio.run(run())


def test_secret_blocking_credential_keyvalue():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Our database password: my-super-secret-password-123.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=7,
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
        assert "secret or credential pattern" in result.reason
        assert "my-super-secret-password" not in result.reason
    asyncio.run(run())


def test_sensitivity_handling():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="This is highly personal medical history.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.HIGH
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.PENDING_APPROVAL
        assert "high sensitivity" in result.reason
    asyncio.run(run())


def test_low_utility_importance():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Nothing important.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=2,  # Below utility threshold of 3
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.DROP_LOW_UTILITY
        assert "importance score" in result.reason
    asyncio.run(run())


def test_low_utility_confidence():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Very low confidence extraction.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.4,  # Below utility threshold of 0.5
            importance=5,
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.DROP_LOW_UTILITY
        assert "confidence" in result.reason
    asyncio.run(run())


def test_save_fallback():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python for backend systems.",
            memory_type=MemoryType.PROCEDURAL,
            confidence=0.9,
            importance=7,
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.SAVE
        assert "passed all deterministic policy checks" in result.reason
    asyncio.run(run())


def test_precedence_secret_over_low_utility():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="sk-test-123456789abcdefghij",  # Secret
            memory_type=MemoryType.SEMANTIC,
            confidence=0.3,   # Low utility
            importance=1,     # Low utility
            sensitivity=Sensitivity.LOW
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
    asyncio.run(run())


def test_precedence_secret_over_sensitivity():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="sk-test-123456789abcdefghij",  # Secret
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.HIGH  # High sensitivity
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
    asyncio.run(run())


def test_precedence_sensitivity_over_low_utility():
    async def run():
        broker = PolicyBroker()
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Sensitive fact.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.3,   # Low utility
            importance=1,     # Low utility
            sensitivity=Sensitivity.HIGH  # High sensitivity
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.PENDING_APPROVAL
    asyncio.run(run())
