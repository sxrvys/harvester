"""Optional process-local hook for the v2 queue's conversion slot."""

from contextlib import nullcontext
from contextvars import ContextVar

processing_scope = ContextVar("harvester_processing_scope", default=nullcontext)
export_options = ContextVar("harvester_export_options", default={})
progress_sink = ContextVar("harvester_progress_sink", default=None)
