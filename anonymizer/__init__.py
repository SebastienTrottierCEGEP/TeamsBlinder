"""
Package d'anonymisation d'examens TeamsBlinder.
"""

from .config import load_config
from .identity import extract_student_identity, MappingTracker
from .file_operations import prepare_student_submission, extract_zip_archives, anonymize_filenames_and_contents
from .agent_harness import AnonymizationAgentHarness

__all__ = [
    "load_config",
    "extract_student_identity",
    "MappingTracker",
    "prepare_student_submission",
    "extract_zip_archives",
    "anonymize_filenames_and_contents",
    "AnonymizationAgentHarness",
]
