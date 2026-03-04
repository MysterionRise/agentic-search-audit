"""Auto-classify search query intent."""

from ..core.types import SearchIntent


class IntentClassifier:
    """Keyword-based intent classifier for search queries."""

    SERVICE_PATTERNS: list[str] = [
        "pickup",
        "delivery",
        "same day",
        "rush",
        "expedited",
        "store hours",
        "shipping",
        "installation",
        "assembly",
        "service",
        "appointment",
        "in-store",
        "curbside",
        "next day",
        "express",
    ]
    NAVIGATION_PATTERNS: list[str] = [
        "login",
        "account",
        "order status",
        "track",
        "help",
        "contact",
        "return",
        "returns",
        "FAQ",
        "about",
        "careers",
        "store locator",
        "sign in",
        "sign up",
        "register",
        "my orders",
        "wishlist",
    ]
    INFORMATIONAL_PATTERNS: list[str] = [
        "return policy",
        "shipping info",
        "how to",
        "faq",
        "size guide",
        "size chart",
        "care instructions",
        "warranty",
        "what is",
        "guide",
        "tutorial",
        "comparison",
        "vs",
        "difference between",
    ]

    def classify(self, query_text: str) -> SearchIntent:
        """Classify query intent based on keyword patterns.

        Args:
            query_text: The search query text.

        Returns:
            Classified SearchIntent. Defaults to PRODUCT.
        """
        text_lower = query_text.lower()

        # Check informational first (more specific patterns)
        for pattern in self.INFORMATIONAL_PATTERNS:
            if pattern.lower() in text_lower:
                return SearchIntent.INFORMATIONAL

        # Check navigation patterns
        for pattern in self.NAVIGATION_PATTERNS:
            if pattern.lower() in text_lower:
                return SearchIntent.NAVIGATION

        # Check service patterns
        for pattern in self.SERVICE_PATTERNS:
            if pattern.lower() in text_lower:
                return SearchIntent.SERVICE

        # Default to product
        return SearchIntent.PRODUCT
