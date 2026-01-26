"""
State Manager - Optimized and Minimal
Handles state transitions and validations using centralized config
Only includes methods that are actually used
"""

from typing import Dict, List, Set, Optional
import logging

from ..models.state import BookingState
from ..config.config import FSM_STATE_DESCRIPTIONS, FSM_STATE_PROGRESS

logger = logging.getLogger(__name__)


class StateManager:
    """Manages FSM state transitions with validation - Minimal and optimized"""
    
    def __init__(self):
        """Initialize state manager with transition rules"""
        
        # Define valid state transitions (FSM graph)
        self.transitions: Dict[BookingState, Set[BookingState]] = {
            BookingState.GREETING: {
                BookingState.INFO_MODE,
                BookingState.SELECTING_SERVICE,
                BookingState.GREETING
            },
            
            BookingState.INFO_MODE: {
                BookingState.SELECTING_SERVICE,
                BookingState.GREETING,
                BookingState.INFO_MODE
            },
            
            BookingState.SELECTING_SERVICE: {
                BookingState.SELECTING_PACKAGE,
                BookingState.INFO_MODE,
                BookingState.GREETING,
                BookingState.SELECTING_SERVICE
            },
            
            BookingState.SELECTING_PACKAGE: {
                BookingState.COLLECTING_DETAILS,
                BookingState.SELECTING_SERVICE,
                BookingState.INFO_MODE,
                BookingState.GREETING,
                BookingState.SELECTING_PACKAGE
            },
            
            BookingState.COLLECTING_DETAILS: {
                BookingState.CONFIRMING,
                BookingState.COLLECTING_DETAILS,
                BookingState.SELECTING_SERVICE,
                BookingState.GREETING
            },
            
            BookingState.CONFIRMING: {
                BookingState.OTP_SENT,
                BookingState.COLLECTING_DETAILS,
                BookingState.GREETING
            },
            
            BookingState.OTP_SENT: {
                BookingState.COMPLETED,
                BookingState.OTP_SENT,
                BookingState.GREETING
            },
            
            BookingState.COMPLETED: {
                BookingState.GREETING
            }
        }
        
        # State categories
        self.booking_flow_states = {
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE,
            BookingState.COLLECTING_DETAILS,
            BookingState.CONFIRMING,
            BookingState.OTP_SENT
        }
        
        self.info_allowed_states = {
            BookingState.GREETING,
            BookingState.INFO_MODE,
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE
        }
    
    def can_transition(self, from_state: BookingState, to_state: BookingState) -> bool:
        """
        Check if transition is valid
        
        Args:
            from_state: Current state
            to_state: Desired next state
            
        Returns:
            True if transition is valid
        """
        if from_state not in self.transitions:
            logger.warning(f"Invalid from_state: {from_state}")
            return False
        
        is_valid = to_state in self.transitions[from_state]
        
        if not is_valid:
            logger.debug(
                f"Invalid transition: {from_state.value} -> {to_state.value}"
            )
        
        return is_valid
    
    def get_valid_transitions(self, current_state: BookingState) -> List[BookingState]:
        """
        Get list of valid next states
        
        Args:
            current_state: Current FSM state
            
        Returns:
            List of valid next states
        """
        return list(self.transitions.get(current_state, [BookingState.GREETING]))
    
    def is_booking_active(self, state: BookingState) -> bool:
        """
        Check if in active booking flow
        
        Args:
            state: Current state
            
        Returns:
            True if in active booking
        """
        return state in self.booking_flow_states
    
    def can_handle_info_query(self, state: BookingState) -> bool:
        """
        Check if info queries allowed in current state
        
        Args:
            state: Current state
            
        Returns:
            True if info queries allowed
        """
        return state in self.info_allowed_states
    
    def get_state_description(self, state: BookingState) -> str:
        """
        Get state description from config
        
        Args:
            state: State to describe
            
        Returns:
            Description string
        """
        return FSM_STATE_DESCRIPTIONS.get(
            state.value.upper(),
            f"Unknown state: {state}"
        )
    
    def get_state_progress(self, state: BookingState) -> int:
        """
        Get progress percentage from config (0-100)
        
        Args:
            state: Current state
            
        Returns:
            Progress percentage
        """
        return FSM_STATE_PROGRESS.get(state.value.upper(), 0)
    
    def validate_state_requirements(self, state: BookingState, intent) -> Dict[str, any]:
        """
        Validate if requirements for state are met
        
        Args:
            state: State to validate
            intent: BookingIntent object
            
        Returns:
            {
                'valid': bool,
                'missing': List[str],
                'can_proceed': bool
            }
        """
        requirements = {
            BookingState.SELECTING_PACKAGE: ['service'],
            BookingState.COLLECTING_DETAILS: ['service', 'package'],
            BookingState.CONFIRMING: [
                'service', 'package', 'name', 'email', 
                'phone', 'date', 'address', 'pincode'
            ],
            BookingState.OTP_SENT: [
                'service', 'package', 'name', 'email',
                'phone', 'date', 'address', 'pincode'
            ]
        }
        
        required = requirements.get(state, [])
        missing = [f for f in required if not getattr(intent, f, None)]
        
        return {
            'valid': len(missing) == 0,
            'missing': missing,
            'can_proceed': len(missing) == 0
        }