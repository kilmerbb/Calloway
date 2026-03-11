"""Command handlers for agent SMS commands.

Each module handles a related group of commands. The main router in
handlers.py dispatches to these based on the classified command type.
"""

from app.pipeline.commands.listing import (
    handle_listing_command,
    handle_listing_query,
    handle_broadcast,
)
from app.pipeline.commands.contact import (
    handle_client_instruction,
    handle_contact_query,
    handle_note_command,
    handle_connect_command,
)
from app.pipeline.commands.status import (
    handle_status_change,
    handle_handoff_return,
)
from app.pipeline.commands.scheduling import (
    handle_schedule_query,
    handle_gap_query,
    handle_trigger_command,
    handle_cascade_command,
)
from app.pipeline.commands.offer import handle_offer_command

__all__ = [
    "handle_listing_command",
    "handle_listing_query",
    "handle_broadcast",
    "handle_client_instruction",
    "handle_contact_query",
    "handle_note_command",
    "handle_connect_command",
    "handle_status_change",
    "handle_handoff_return",
    "handle_schedule_query",
    "handle_gap_query",
    "handle_trigger_command",
    "handle_cascade_command",
    "handle_offer_command",
]
