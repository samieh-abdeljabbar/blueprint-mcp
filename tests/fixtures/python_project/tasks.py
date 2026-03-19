"""Celery tasks for testing."""

from celery import shared_task


@shared_task
def send_welcome_email(user_id: int):
    """Send welcome email to new user."""
    pass


@shared_task
def process_upload(file_path: str):
    """Process an uploaded file."""
    pass


def _format_email_body(user_name: str) -> str:
    """Private helper — should not be detected."""
    return f"Welcome {user_name}"
