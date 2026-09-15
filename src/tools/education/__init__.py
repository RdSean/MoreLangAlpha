"""First-party education tools exposed to the host-side agents."""

from src.tools.education.homework import education_create_homework

EDUCATION_TOOLS = [education_create_homework]

__all__ = ["education_create_homework", "EDUCATION_TOOLS"]
