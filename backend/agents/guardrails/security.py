"""
Security Guardrails for ReAct Agent

Industry-standard protections against prompt injection, abuse, and unauthorized access.
"""
import logging
import time
from typing import Optional, Dict, Any
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PromptInjectionDetector:
    """Detect common prompt injection attack patterns."""

    INJECTION_PATTERNS = [
        # Instruction override attempts
        'ignore previous',
        'ignore all previous',
        'ignore all instructions',
        'disregard previous',
        'forget previous',
        'forget everything',
        'new instructions',
        'new instruction',

        # Role manipulation
        'you are now',
        'act as',
        'pretend to be',
        'simulate',
        'you must',

        # System prompt extraction
        'show me your',
        'what are your instructions',
        'what is your system prompt',
        'repeat your instructions',
        'tell me your rules',

        # Command injection
        'execute',
        'run command',
        'system(',
        'eval(',
        'exec(',
        '__import__',

        # Data extraction
        'show all',
        'list all',
        'dump',
        'export',
    ]

    @classmethod
    def detect(cls, text: str) -> tuple[bool, Optional[str]]:
        """
        Detect potential prompt injection.

        Args:
            text: User input to analyze

        Returns:
            Tuple of (is_injection, matched_pattern)
        """
        text_lower = text.lower()

        for pattern in cls.INJECTION_PATTERNS:
            if pattern in text_lower:
                logger.warning(
                    f"SECURITY: Injection pattern detected: '{pattern}' in input: {text[:100]}"
                )
                return True, pattern

        return False, None


class RateLimiter:
    """
    Rate limiting per user to prevent abuse.

    Implements sliding window rate limiting.
    """

    def __init__(self, max_calls_per_minute: int = 10, max_calls_per_hour: int = 100):
        self.max_calls_per_minute = max_calls_per_minute
        self.max_calls_per_hour = max_calls_per_hour

        # Track calls per user
        self._minute_calls: Dict[str, list] = defaultdict(list)
        self._hour_calls: Dict[str, list] = defaultdict(list)

    def check_rate_limit(self, user_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if user has exceeded rate limits.

        Args:
            user_id: Unique user identifier

        Returns:
            Tuple of (is_allowed, error_message)
        """
        now = time.time()

        # Clean old entries
        self._minute_calls[user_id] = [
            t for t in self._minute_calls[user_id]
            if now - t < 60
        ]
        self._hour_calls[user_id] = [
            t for t in self._hour_calls[user_id]
            if now - t < 3600
        ]

        # Check minute limit
        if len(self._minute_calls[user_id]) >= self.max_calls_per_minute:
            logger.warning(f"SECURITY: Rate limit exceeded (minute) for user={user_id}")
            return False, f"Rate limit exceeded. Maximum {self.max_calls_per_minute} requests per minute."

        # Check hour limit
        if len(self._hour_calls[user_id]) >= self.max_calls_per_hour:
            logger.warning(f"SECURITY: Rate limit exceeded (hour) for user={user_id}")
            return False, f"Rate limit exceeded. Maximum {self.max_calls_per_hour} requests per hour."

        # Record this call
        self._minute_calls[user_id].append(now)
        self._hour_calls[user_id].append(now)

        return True, None

    def reset_user(self, user_id: str):
        """Reset rate limits for a specific user."""
        self._minute_calls.pop(user_id, None)
        self._hour_calls.pop(user_id, None)


class InputValidator:
    """Validate and sanitize user inputs."""

    MAX_INPUT_LENGTH = 5000  # Characters
    MAX_WORDS = 1000

    @classmethod
    def validate(cls, text: str) -> tuple[bool, Optional[str]]:
        """
        Validate user input.

        Args:
            text: User input to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check length
        if len(text) > cls.MAX_INPUT_LENGTH:
            return False, f"Input too long. Maximum {cls.MAX_INPUT_LENGTH} characters."

        # Check word count
        word_count = len(text.split())
        if word_count > cls.MAX_WORDS:
            return False, f"Input too long. Maximum {cls.MAX_WORDS} words."

        # Check for null bytes (can cause issues)
        if '\x00' in text:
            return False, "Input contains invalid characters."

        return True, None


class GuardrailsManager:
    """
    Central manager for all security guardrails.

    Coordinates injection detection, rate limiting, and input validation.
    """

    def __init__(
        self,
        enable_injection_detection: bool = True,
        enable_rate_limiting: bool = True,
        enable_input_validation: bool = True,
        max_calls_per_minute: int = 10,
        max_calls_per_hour: int = 100
    ):
        self.enable_injection_detection = enable_injection_detection
        self.enable_rate_limiting = enable_rate_limiting
        self.enable_input_validation = enable_input_validation

        self.injection_detector = PromptInjectionDetector()
        self.rate_limiter = RateLimiter(max_calls_per_minute, max_calls_per_hour)
        self.input_validator = InputValidator()

        # Security event log
        self.security_events = []

    def check_input(
        self,
        text: str,
        user_id: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Run all guardrail checks on user input.

        Args:
            text: User input to check
            user_id: Optional user identifier for rate limiting

        Returns:
            Tuple of (is_safe, error_message)
        """
        # Input validation
        if self.enable_input_validation:
            is_valid, error = self.input_validator.validate(text)
            if not is_valid:
                self._log_security_event('input_validation_failed', user_id, error)
                return False, error

        # Prompt injection detection
        if self.enable_injection_detection:
            is_injection, pattern = self.injection_detector.detect(text)
            if is_injection:
                self._log_security_event('injection_detected', user_id, pattern)
                return False, "I can't process that request. Please rephrase without special instructions."

        # Rate limiting
        if self.enable_rate_limiting and user_id:
            is_allowed, error = self.rate_limiter.check_rate_limit(user_id)
            if not is_allowed:
                self._log_security_event('rate_limit_exceeded', user_id, error)
                return False, error

        return True, None

    def _log_security_event(self, event_type: str, user_id: Optional[str], details: Any):
        """Log security event for monitoring."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'details': details
        }
        self.security_events.append(event)
        logger.warning(f"SECURITY_EVENT: {event}")

        # Keep only last 1000 events
        if len(self.security_events) > 1000:
            self.security_events = self.security_events[-1000:]

    def get_security_events(self, last_n: int = 100) -> list:
        """Get recent security events for monitoring."""
        return self.security_events[-last_n:]


# Global instance
_guardrails_manager = None


def get_guardrails() -> GuardrailsManager:
    """Get global guardrails manager instance."""
    global _guardrails_manager
    if _guardrails_manager is None:
        _guardrails_manager = GuardrailsManager(
            enable_injection_detection=True,
            enable_rate_limiting=True,
            enable_input_validation=True,
            max_calls_per_minute=10,
            max_calls_per_hour=100
        )
    return _guardrails_manager
