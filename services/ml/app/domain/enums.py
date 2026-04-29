from enum import Enum


class CameraRole(str, Enum):
    """Role of the camera in the parking system."""
    ENTRY = "entry"
    EXIT = "exit"


class PipelineStatus(str, Enum):
    """Status of the processing pipeline."""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
