"""
HITL Core Infrastructure

Provides the foundational classes and methods for Human-in-the-Loop interactions.

DEPLOYMENT NOTES:
- Uses in-memory storage (dicts) for active_waits and checkpoints
- Safe for single-process AsyncIO deployment (default uvicorn setup)
- For multi-process deployment (--workers > 1), replace with Redis
- For production at scale, consider external state store (Redis/DynamoDB)
"""

import asyncio
import time
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime


class HITLCore:
    """
    Core HITL infrastructure for pausing agent execution and waiting for user input.

    This class provides:
    - Checkpointing: Save/restore agent state
    - Panel injection: Send panels to frontend for user interaction
    - User input waiting: Pause execution until user responds
    """

    def __init__(self):
        """Initialize HITL core with in-memory storage."""
        # Active waits: agent_id -> wait info
        self.active_waits: Dict[str, Dict[str, Any]] = {}

        # Checkpoints: checkpoint_id -> state data
        self.checkpoints: Dict[str, Dict[str, Any]] = {}

        # Callback for sending messages to frontend
        self.send_callback: Optional[Callable] = None

    def set_send_callback(self, callback: Callable):
        """
        Set the callback function for sending messages to frontend.

        Args:
            callback: Async function that sends messages to frontend
        """
        self.send_callback = callback

    async def wait_for_user_input(
        self,
        agent_id: str,
        panel_type: str,
        panel_data: Dict[str, Any],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Pause agent execution and wait for user input.

        This is the main HITL method. It:
        1. Creates a checkpoint of current state
        2. Sends panel to frontend
        3. Waits for user response (or timeout)
        4. Returns user response

        Args:
            agent_id: Unique identifier for the agent
            panel_type: Type of panel to show (e.g., 'approval', 'field_mapping')
            panel_data: Data to populate the panel
            timeout: Max wait time in seconds (default 5 minutes)

        Returns:
            User response data or timeout status
        """
        # Create checkpoint
        checkpoint_id = self.checkpoint(agent_id, panel_data)

        # Create event for signaling response received
        wait_event = asyncio.Event()

        # Store wait info
        self.active_waits[agent_id] = {
            'event': wait_event,
            'checkpoint_id': checkpoint_id,
            'timestamp': time.time(),
            'response': None
        }

        # Send panel to frontend
        await self._send_to_frontend({
            'type': 'show_panel',
            'panel_type': panel_type,
            'data': panel_data,
            'agent_id': agent_id
        })

        # Wait for user response (with timeout)
        try:
            await asyncio.wait_for(wait_event.wait(), timeout=timeout)
            response = self.active_waits[agent_id]['response']

            # Clean up
            del self.active_waits[agent_id]

            return response

        except asyncio.TimeoutError:
            # Clean up on timeout
            if agent_id in self.active_waits:
                del self.active_waits[agent_id]

            return {
                'status': 'timeout',
                'message': f'User did not respond within {timeout} seconds'
            }

    async def receive_user_input(self, agent_id: str, response: Dict[str, Any]):
        """
        Receive user input and resume agent execution.

        Called when frontend sends user response.

        Args:
            agent_id: Agent identifier
            response: User's response data
        """
        if agent_id in self.active_waits:
            # Store response
            self.active_waits[agent_id]['response'] = response

            # Signal that response is ready
            self.active_waits[agent_id]['event'].set()
        else:
            print(f"Warning: Received input for unknown agent {agent_id}")

    def checkpoint(self, agent_id: str, state_data: Dict[str, Any]) -> str:
        """
        Create a checkpoint of current agent state.

        Args:
            agent_id: Agent identifier
            state_data: Data to save

        Returns:
            Checkpoint ID
        """
        checkpoint_id = f"{agent_id}_{uuid.uuid4().hex[:8]}"

        self.checkpoints[checkpoint_id] = {
            'agent_id': agent_id,
            'timestamp': datetime.now().isoformat(),
            'state_data': state_data
        }

        return checkpoint_id

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Restore agent state from checkpoint.

        Args:
            checkpoint_id: Checkpoint to restore

        Returns:
            Checkpoint data or None if not found
        """
        return self.checkpoints.get(checkpoint_id)

    def clear_old_checkpoints(self, max_age_seconds: int = 3600):
        """
        Clean up old checkpoints (older than max_age_seconds).

        Args:
            max_age_seconds: Max age in seconds (default 1 hour)
        """
        current_time = time.time()
        to_delete = []

        for checkpoint_id, checkpoint in self.checkpoints.items():
            timestamp = datetime.fromisoformat(checkpoint['timestamp']).timestamp()
            if current_time - timestamp > max_age_seconds:
                to_delete.append(checkpoint_id)

        for checkpoint_id in to_delete:
            del self.checkpoints[checkpoint_id]

        if to_delete:
            print(f"Cleaned up {len(to_delete)} old checkpoints")

    async def _send_to_frontend(self, message: Dict[str, Any]):
        """
        Send message to frontend.

        Args:
            message: Message to send
        """
        if self.send_callback:
            await self.send_callback(message)
        else:
            print("Warning: No send callback configured, message not sent")
            print(f"Message: {message}")

    def get_active_waits(self) -> Dict[str, Dict[str, Any]]:
        """Get all active waits (for debugging/monitoring)."""
        return {
            agent_id: {
                'checkpoint_id': wait['checkpoint_id'],
                'timestamp': wait['timestamp'],
                'waiting_for': time.time() - wait['timestamp']
            }
            for agent_id, wait in self.active_waits.items()
        }


# Global instance (singleton pattern)
hitl_core = HITLCore()
