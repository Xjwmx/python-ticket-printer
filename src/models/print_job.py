# src/models/print_job.py
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
import json
from pathlib import Path


class PrintJobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # Added new status

    def is_terminal(self) -> bool:
        """Check if this is a terminal status"""
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}

    def is_active(self) -> bool:
        """Check if job is actively being processed"""
        return self in {self.PENDING, self.PROCESSING}


@dataclass
class PrintJob:
    """Represents a print job for one or more orders"""

    id: str  # Unique identifier for the print job
    order_ids: List[str]  # List of Shopify order IDs
    printer_name: str
    copies: int
    created_at: datetime
    status: PrintJobStatus
    pdf_content: Optional[bytes] = None
    error_message: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.now)
    attempts: int = 0
    max_attempts: int = 3
    output_path: Optional[Path] = None

    def __post_init__(self):
        """Validate job data after initialization"""
        if not self.id:
            raise ValueError("Job ID cannot be empty")
        if not self.order_ids:
            raise ValueError("Order IDs cannot be empty")
        if self.copies < 1:
            raise ValueError("Copies must be at least 1")
        if not self.printer_name:
            raise ValueError("Printer name cannot be empty")

    @classmethod
    def create(
        cls,
        order_ids: List[str],
        printer_name: str,
        copies: int = 1,
        max_attempts: int = 3,
    ) -> "PrintJob":
        """Create a new print job"""
        now = datetime.now()
        return cls(
            id=str(uuid4()),
            order_ids=order_ids,
            printer_name=printer_name,
            copies=copies,
            created_at=now,
            updated_at=now,
            status=PrintJobStatus.PENDING,
            max_attempts=max_attempts,
        )

    def update_status(
        self, status: PrintJobStatus, error: Optional[str] = None
    ) -> None:
        """Update job status and related fields"""
        self.status = status
        self.updated_at = datetime.now()

        if error:
            self.error_message = error

        if status == PrintJobStatus.PROCESSING:
            self.attempts += 1

    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return (
            self.status in {PrintJobStatus.FAILED, PrintJobStatus.PENDING}
            and self.attempts < self.max_attempts
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for storage"""
        return {
            "id": self.id,
            "order_ids": self.order_ids,
            "printer_name": self.printer_name,
            "copies": self.copies,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "error_message": self.error_message,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "output_path": str(self.output_path) if self.output_path else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrintJob":
        """Create job from dictionary"""
        # Convert output_path back to Path if present
        output_path = data.get("output_path")
        if output_path:
            output_path = Path(output_path)

        return cls(
            id=data["id"],
            order_ids=data["order_ids"],
            printer_name=data["printer_name"],
            copies=data["copies"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", data["created_at"])
            ),
            status=PrintJobStatus(data["status"]),
            error_message=data.get("error_message"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
            output_path=output_path,
        )

    def to_json_file(self, path: Path) -> None:
        """Save job metadata to JSON file"""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json_file(cls, path: Path) -> "PrintJob":
        """Load job metadata from JSON file"""
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def __str__(self) -> str:
        """Human readable string representation"""
        return (
            f"PrintJob(id={self.id}, "
            f"orders={len(self.order_ids)}, "
            f"printer={self.printer_name}, "
            f"status={self.status.value}, "
            f"attempts={self.attempts}/{self.max_attempts})"
        )

    def duration(self) -> float:
        """Get job duration in seconds"""
        return (self.updated_at - self.created_at).total_seconds()

    def age(self) -> float:
        """Get job age in seconds"""
        return (datetime.now() - self.created_at).total_seconds()
