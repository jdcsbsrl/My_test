"""Test ERP test-case generation package with lazy public exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .utils.knowledge_retriever import KnowledgeRetriever
    from .utils.test_case_generator import TestCaseGenerator

__all__ = [
    "TestCaseGenerator",
    "KnowledgeRetriever",
]


def __getattr__(name: str):
    if name == "KnowledgeRetriever":
        from .utils.knowledge_retriever import KnowledgeRetriever

        return KnowledgeRetriever
    if name == "TestCaseGenerator":
        from .utils.test_case_generator import TestCaseGenerator

        return TestCaseGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
