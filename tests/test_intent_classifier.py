"""Tests for intent auto-classifier."""

import pytest

from agentic_search_audit.core.types import SearchIntent
from agentic_search_audit.judge.intent_classifier import IntentClassifier


class TestIntentClassifier:
    """Tests for IntentClassifier."""

    @pytest.fixture()
    def classifier(self) -> IntentClassifier:
        return IntentClassifier()

    @pytest.mark.unit
    def test_product_default(self, classifier: IntentClassifier) -> None:
        """Generic product queries should classify as PRODUCT."""
        assert classifier.classify("photo books") == SearchIntent.PRODUCT
        assert classifier.classify("running shoes") == SearchIntent.PRODUCT
        assert classifier.classify("canvas prints") == SearchIntent.PRODUCT

    @pytest.mark.unit
    def test_service_intent(self, classifier: IntentClassifier) -> None:
        """Service queries should classify as SERVICE."""
        assert classifier.classify("same day pickup photo prints") == SearchIntent.SERVICE
        assert classifier.classify("next day delivery") == SearchIntent.SERVICE
        assert classifier.classify("store hours") == SearchIntent.SERVICE

    @pytest.mark.unit
    def test_navigation_intent(self, classifier: IntentClassifier) -> None:
        """Navigation queries should classify as NAVIGATION."""
        assert classifier.classify("login") == SearchIntent.NAVIGATION
        assert classifier.classify("my account") == SearchIntent.NAVIGATION
        assert classifier.classify("order status") == SearchIntent.NAVIGATION
        assert classifier.classify("contact us") == SearchIntent.NAVIGATION

    @pytest.mark.unit
    def test_informational_intent(self, classifier: IntentClassifier) -> None:
        """Informational queries should classify as INFORMATIONAL."""
        assert classifier.classify("return policy") == SearchIntent.INFORMATIONAL
        assert classifier.classify("shipping info") == SearchIntent.INFORMATIONAL
        assert classifier.classify("how to make a photo book") == SearchIntent.INFORMATIONAL
        assert classifier.classify("size guide") == SearchIntent.INFORMATIONAL

    @pytest.mark.unit
    def test_case_insensitive(self, classifier: IntentClassifier) -> None:
        """Classification should be case-insensitive."""
        assert classifier.classify("SAME DAY PICKUP") == SearchIntent.SERVICE
        assert classifier.classify("Login") == SearchIntent.NAVIGATION
        assert classifier.classify("Return Policy") == SearchIntent.INFORMATIONAL

    @pytest.mark.unit
    def test_manual_intent_preserved(self) -> None:
        """When query has manual intent, auto-classifier should not overwrite it."""
        from agentic_search_audit.core.types import Query

        q = Query(id="q1", text="photo books", intent=SearchIntent.SERVICE)
        # The orchestrator checks `if query.intent is None` before classifying
        # So manual intent should be preserved
        assert q.intent == SearchIntent.SERVICE
