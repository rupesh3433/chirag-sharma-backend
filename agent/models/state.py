"""
Booking States Enum
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
    
    def is_booking_flow(self) -> bool:
        """Check if state is part of booking flow"""
        booking_states = [
            self.SELECTING_SERVICE,
            self.SELECTING_PACKAGE,
            self.COLLECTING_DETAILS,
            self.CONFIRMING,
            self.OTP_SENT,
            self.COMPLETED
        ]
        return self in booking_states
    
    def get_next_expected(self) -> str:
        """Get what's expected next in this state"""
        expectations = {
            self.GREETING: "greeting or booking intent",
            self.INFO_MODE: "information query",
            self.SELECTING_SERVICE: "service selection",
            self.SELECTING_PACKAGE: "package selection",
            self.COLLECTING_DETAILS: "personal details",
            self.CONFIRMING: "confirmation (yes/no)",
            self.OTP_SENT: "OTP verification",
            self.COMPLETED: "booking completion"
        }
        return expectations.get(self, "unknown")