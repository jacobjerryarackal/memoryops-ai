import pytest
import asyncio
from app.domain import CandidateMemory, MemoryRecord, PolicyDecision, Sensitivity, MemoryType
from app.policy import PolicyBroker, SlotCardinality, StaticSlotRegistry
from app.repositories import InMemoryMemoryRepository

# ------------------------------------------------------------
# TEST DOUBLES / SPYING REPOSITORY
# ------------------------------------------------------------

class SpyingRepository(InMemoryMemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.called_slots = []

    async def get_active_by_slot(
        self,
        tenant_id: str,
        user_id: str,
        memory_type: MemoryType,
        identity_slot: str,
    ):
        self.called_slots.append((tenant_id, user_id, memory_type, identity_slot))
        return await super().get_active_by_slot(tenant_id, user_id, memory_type, identity_slot)


# ------------------------------------------------------------
# SLOT REGISTRY TESTS
# ------------------------------------------------------------

def test_static_slot_registry_vocabulary():
    registry = StaticSlotRegistry()
    
    # 1. Semantic slots
    assert registry.get_cardinality(MemoryType.SEMANTIC, "profession") == SlotCardinality.SINGLE
    assert registry.get_cardinality(MemoryType.SEMANTIC, "residence") == SlotCardinality.SINGLE
    assert registry.get_cardinality(MemoryType.SEMANTIC, "technology_stack") == SlotCardinality.MULTI
    assert registry.get_cardinality(MemoryType.SEMANTIC, "project_built") == SlotCardinality.MULTI

    # 2. Procedural slots
    assert registry.get_cardinality(MemoryType.PROCEDURAL, "explanation_style") == SlotCardinality.SINGLE
    assert registry.get_cardinality(MemoryType.PROCEDURAL, "formatting_hashtags") == SlotCardinality.SINGLE
    assert registry.get_cardinality(MemoryType.PROCEDURAL, "formatting_hyphens") == SlotCardinality.SINGLE

    # 3. Episodic slots and unregistered slots
    assert registry.get_cardinality(MemoryType.EPISODIC, "hackathon_event") is None
    assert registry.get_cardinality(MemoryType.SEMANTIC, "favorite_color") is None

    # 4. Exact matching is enforced (no lowercase normalization of inputs)
    assert registry.get_cardinality(MemoryType.SEMANTIC, "Profession") is None

    # 5. Registry exposes no mutation behavior
    assert not hasattr(registry, "add_slot")
    assert not hasattr(registry, "remove_slot")


# ------------------------------------------------------------
# POLICY BROKER TESTS
# ------------------------------------------------------------

def test_secret_blocking_openai_key():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Remember that my API key is sk-test-123456789abcdefghij.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW,
            identity_slot="profession"  # Valid SINGLE slot
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
        assert "secret or credential pattern" in result.reason
        assert "sk-test" not in result.reason
        # Verify repository lookup was skipped (short-circuited)
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_secret_blocking_credential_keyvalue():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Our database password: my-super-secret-password-123.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=7,
            sensitivity=Sensitivity.LOW,
            identity_slot="profession"
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
        # Verify repository lookup was skipped
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_sensitivity_handling():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="This is highly personal medical history.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.HIGH,
            identity_slot="profession"
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.PENDING_APPROVAL
        assert "high sensitivity" in result.reason
        # Verify repository lookup was skipped
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_save_fallback_none_slot():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python for backend systems.",
            memory_type=MemoryType.PROCEDURAL,
            confidence=0.9,
            importance=7,
            sensitivity=Sensitivity.LOW,
            identity_slot=None  # identity_slot is None
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.SAVE
        assert "No mutation coordinate is assigned" in result.reason
        # Verify repository lookup was skipped
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_save_fallback_unknown_slot():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="My favorite color is blue.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=7,
            sensitivity=Sensitivity.LOW,
            identity_slot="favorite_color"  # Unregistered slot
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.SAVE
        assert "identity slot is unregistered" in result.reason
        # Verify repository lookup was skipped
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_save_fallback_multi_slot():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="I know Python and FastAPI.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=7,
            sensitivity=Sensitivity.LOW,
            identity_slot="technology_stack"  # Known MULTI slot
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.SAVE
        assert "registered as multi-valued" in result.reason
        # Verify repository lookup was skipped
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_precedence_secret_over_sensitivity():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="sk-test-123456789abcdefghij",  # Secret
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.HIGH,  # High sensitivity
            identity_slot="profession"
        )
        result = await broker.evaluate(candidate)
        assert result.decision == PolicyDecision.BLOCK
        assert len(repo.called_slots) == 0
    asyncio.run(run())


def test_single_slot_gating_scenarios():
    async def run():
        repo = SpyingRepository()
        broker = PolicyBroker(repository=repo)
        tenant = "tenant_a"
        user = "user_a"

        # Candidate Memory targeting single-valued "profession"
        candidate = CandidateMemory(
            tenant_id=tenant,
            user_id=user,
            content="AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW,
            identity_slot="profession"
        )

        # SCENARIO 1: Zero active occupants (vacant slot)
        res1 = await broker.evaluate(candidate)
        assert res1.decision == PolicyDecision.SAVE
        assert "vacant" in res1.reason
        assert res1.target_memory_id is None
        assert repo.called_slots == [(tenant, user, MemoryType.SEMANTIC, "profession")]

        # SCENARIO 2: Exactly one active occupant (target for update)
        repo.called_slots.clear()
        rec1 = MemoryRecord(
            tenant_id=tenant,
            user_id=user,
            content="Software Engineer",
            memory_type=MemoryType.SEMANTIC,
            identity_slot="profession",
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="admission"
        )
        created1 = await repo.create(rec1)

        res2 = await broker.evaluate(candidate)
        assert res2.decision == PolicyDecision.UPDATE_EXISTING
        assert res2.target_memory_id == created1.id
        assert repo.called_slots == [(tenant, user, MemoryType.SEMANTIC, "profession")]

        # SCENARIO 2b: Identical content still triggers UPDATE_EXISTING
        repo.called_slots.clear()
        candidate_same_content = CandidateMemory(
            tenant_id=tenant,
            user_id=user,
            content="Software Engineer",  # Identical content
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW,
            identity_slot="profession"
        )
        res2b = await broker.evaluate(candidate_same_content)
        assert res2b.decision == PolicyDecision.UPDATE_EXISTING
        assert res2b.target_memory_id == created1.id

        # SCENARIO 3: Anomalous multi-occupancy (at least two active occupants)
        repo.called_slots.clear()
        rec2 = MemoryRecord(
            tenant_id=tenant,
            user_id=user,
            content="Web Developer",
            memory_type=MemoryType.SEMANTIC,
            identity_slot="profession",
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="admission"
        )
        await repo.create(rec2)

        res3 = await broker.evaluate(candidate)
        assert res3.decision == PolicyDecision.PENDING_APPROVAL
        assert res3.target_memory_id is None
        assert "anomalous multiple active occupants" in res3.reason
        assert repo.called_slots == [(tenant, user, MemoryType.SEMANTIC, "profession")]

    asyncio.run(run())
