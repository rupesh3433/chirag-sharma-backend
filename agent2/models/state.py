"""
Booking States Enum - Simplified
"""

from enum import Enum


class BookingState(Enum):
    """FSM States for booking flow"""
    
    GREETING = "greeting"
    INFO_MODE = "info_mode"
    SELECTING_SERVICE = "selecting_service"
    SELECTING_PACKAGE = "selecting_package"
    COLLECTING_DETAILS = "collecting_details"
    CONFIRMING = "confirming"
    OTP_SENT = "otp_sent"
    COMPLETED = "completed"
    
    @classmethod
    def from_string(cls, state_str: str) -> 'BookingState':
        """Convert string to BookingState enum"""
        state_map = {state.value: state for state in cls}
        return state_map.get(state_str, cls.GREETING)