"""
MongoDB document models using Beanie ODM
"""

from typing import List, Type

from beanie import Document as BeanieDocument

from .user import User
from .chat import ChatSession, ChatMessage
from .task import Task, DeepResearchTask
from .research import ResearchSource, Evidence
from .system_settings import SystemSettings
from .history import HistoryEvent, HistoryEventFactory, HistoryQuery
from .document import Document as DocumentModel
from .review_job import ReviewJob
from .validation_report import ValidationReport
from .password_reset import PasswordResetToken

# List of all document models for Beanie initialization
def get_document_models() -> List[Type[BeanieDocument]]:
    """Get all document models for Beanie initialization"""
    return [
        User,
        ChatSession,
        ChatMessage,
        Task,
        DeepResearchTask,
        ResearchSource,
        Evidence,
        SystemSettings,
        HistoryEvent,
        DocumentModel,
        ReviewJob,
        ValidationReport,
        PasswordResetToken,
    ]

__all__ = [
    "User",
    "ChatSession",
    "ChatMessage",
    "Task",
    "DeepResearchTask",
    "ResearchSource",
    "Evidence",
    "SystemSettings",
    "HistoryEvent",
    "HistoryEventFactory",
    "HistoryQuery",
    "DocumentModel",
    "ReviewJob",
    "ValidationReport",
    "PasswordResetToken",
    "get_document_models",
]
