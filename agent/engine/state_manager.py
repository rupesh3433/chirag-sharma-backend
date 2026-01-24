"""
State Manager - Handles state transitions and validations
"""

from typing import Dict, List, Optional, Set
from enum import Enum
import logging

from ..models.state import BookingState

logger = logging.getLogger(__name__)


class StateManager:
    """Manages FSM state transitions with validation"""
    
    def __init__(self):
        """Initialize state manager with transition rules"""
        
        # Define valid state transitions (FSM graph)
        self.transitions: Dict[BookingState, Set[BookingState]] = {
            BookingState.GREETING: {
                BookingState.INFO_MODE,
                BookingState.SELECTING_SERVICE,
                BookingState.GREETING  # Can stay in greeting
            },
            
            BookingState.INFO_MODE: {
                BookingState.SELECTING_SERVICE,
                BookingState.GREETING,
                BookingState.INFO_MODE  # Can stay for multiple queries
            },
            
            BookingState.SELECTING_SERVICE: {
                BookingState.SELECTING_PACKAGE,
                BookingState.INFO_MODE,  # Can ask questions
                BookingState.GREETING,  # Can restart
                BookingState.SELECTING_SERVICE  # Can retry
            },
            
            BookingState.SELECTING_PACKAGE: {
                BookingState.COLLECTING_DETAILS,
                BookingState.SELECTING_SERVICE,  # Can go back
                BookingState.INFO_MODE,  # Can ask questions
                BookingState.GREETING,  # Can restart
                BookingState.SELECTING_PACKAGE  # Can retry
            },
            
            BookingState.COLLECTING_DETAILS: {
                BookingState.CONFIRMING,
                BookingState.COLLECTING_DETAILS,  # Stay for more details
                BookingState.SELECTING_SERVICE,  # Can go back
                BookingState.GREETING  # Can restart
            },
            
            BookingState.CONFIRMING: {
                BookingState.OTP_SENT,
                BookingState.COLLECTING_DETAILS,  # Go back to edit
                BookingState.GREETING  # Can cancel
            },
            
            BookingState.OTP_SENT: {
                BookingState.COMPLETED,
                BookingState.OTP_SENT,  # Retry OTP
                BookingState.GREETING  # Can cancel
            },
            
            BookingState.COMPLETED: {
                BookingState.GREETING  # Start new booking
            }
        }
        
        # States that represent active booking flow
        self.booking_flow_states = {
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE,
            BookingState.COLLECTING_DETAILS,
            BookingState.CONFIRMING,
            BookingState.OTP_SENT
        }
        
        # States that allow information queries
        self.info_allowed_states = {
            BookingState.GREETING,
            BookingState.INFO_MODE,
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE
        }
        
        # Terminal states (end states)
        self.terminal_states = {
            BookingState.COMPLETED
        }
    
    def get_valid_transitions(self, current_state: BookingState) -> List[BookingState]:
        """
        Get list of valid next states from current state
        
        Args:
            current_state: Current FSM state
            
        Returns:
            List of valid next states
        """
        if current_state not in self.transitions:
            logger.warning(f"Unknown state: {current_state}")
            return [BookingState.GREETING]
        
        return list(self.transitions[current_state])
    
    def can_transition(self, from_state: BookingState, to_state: BookingState) -> bool:
        """
        Check if transition from one state to another is valid
        
        Args:
            from_state: Current state
            to_state: Desired next state
            
        Returns:
            True if transition is valid, False otherwise
        """
        if from_state not in self.transitions:
            logger.warning(f"Invalid from_state: {from_state}")
            return False
        
        valid_transitions = self.transitions[from_state]
        is_valid = to_state in valid_transitions
        
        if not is_valid:
            logger.warning(
                f"Invalid transition: {from_state.value} -> {to_state.value}. "
                f"Valid: {[s.value for s in valid_transitions]}"
            )
        
        return is_valid
    
    def get_default_state(self) -> BookingState:
        """
        Get default starting state
        
        Returns:
            Default state (GREETING)
        """
        return BookingState.GREETING
    
    def get_completion_state(self) -> BookingState:
        """
        Get final completion state
        
        Returns:
            Completion state (COMPLETED)
        """
        return BookingState.COMPLETED
    
    def is_booking_active(self, state: BookingState) -> bool:
        """
        Check if state represents active booking flow
        
        Args:
            state: Current state
            
        Returns:
            True if in active booking, False otherwise
        """
        return state in self.booking_flow_states
    
    def is_terminal_state(self, state: BookingState) -> bool:
        """
        Check if state is terminal (end state)
        
        Args:
            state: State to check
            
        Returns:
            True if terminal state, False otherwise
        """
        return state in self.terminal_states
    
    def can_handle_info_query(self, state: BookingState) -> bool:
        """
        Check if info queries are allowed in current state
        
        Args:
            state: Current state
            
        Returns:
            True if info queries allowed, False otherwise
        """
        return state in self.info_allowed_states
    
    def get_next_required_state(self, current_state: BookingState, intent_complete: bool = False) -> Optional[BookingState]:
        """
        Get next required state in linear booking flow
        
        Args:
            current_state: Current state
            intent_complete: Whether booking intent is complete
            
        Returns:
            Next required state or None
        """
        flow_sequence = [
            BookingState.GREETING,
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE,
            BookingState.COLLECTING_DETAILS,
            BookingState.CONFIRMING,
            BookingState.OTP_SENT,
            BookingState.COMPLETED
        ]
        
        try:
            current_idx = flow_sequence.index(current_state)
            if current_idx < len(flow_sequence) - 1:
                return flow_sequence[current_idx + 1]
        except ValueError:
            logger.warning(f"State {current_state} not in linear flow")
        
        return None
    
    def get_previous_state(self, current_state: BookingState) -> Optional[BookingState]:
        """
        Get previous state in linear booking flow (for going back)
        
        Args:
            current_state: Current state
            
        Returns:
            Previous state or None
        """
        flow_sequence = [
            BookingState.GREETING,
            BookingState.SELECTING_SERVICE,
            BookingState.SELECTING_PACKAGE,
            BookingState.COLLECTING_DETAILS,
            BookingState.CONFIRMING,
            BookingState.OTP_SENT
        ]
        
        try:
            current_idx = flow_sequence.index(current_state)
            if current_idx > 0:
                return flow_sequence[current_idx - 1]
        except ValueError:
            pass
        
        return None
    
    def validate_state_requirements(self, state: BookingState, intent) -> Dict[str, any]:
        """
        Validate if requirements for a state are met
        
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
            BookingState.GREETING: [],
            BookingState.INFO_MODE: [],
            BookingState.SELECTING_SERVICE: [],
            BookingState.SELECTING_PACKAGE: ['service'],
            BookingState.COLLECTING_DETAILS: ['service', 'package'],
            BookingState.CONFIRMING: ['service', 'package', 'name', 'email', 'phone', 'date', 'address', 'pincode', 'service_country'],
            BookingState.OTP_SENT: ['service', 'package', 'name', 'email', 'phone', 'date', 'address', 'pincode', 'service_country'],
            BookingState.COMPLETED: []
        }
        
        required = requirements.get(state, [])
        missing = []
        
        for field in required:
            if not getattr(intent, field, None):
                missing.append(field)
        
        return {
            'valid': len(missing) == 0,
            'missing': missing,
            'can_proceed': len(missing) == 0
        }
    
    def suggest_state_recovery(self, current_state: BookingState, error: str) -> BookingState:
        """
        Suggest state to recover to after error
        
        Args:
            current_state: State where error occurred
            error: Error description
            
        Returns:
            Suggested recovery state
        """
        # For most errors, go back to greeting
        if 'critical' in error.lower() or 'fatal' in error.lower():
            return BookingState.GREETING
        
        # For validation errors, stay in current state
        if 'validation' in error.lower() or 'invalid' in error.lower():
            return current_state
        
        # For missing data, go to appropriate collection state
        if 'missing' in error.lower():
            if current_state in [BookingState.CONFIRMING, BookingState.OTP_SENT]:
                return BookingState.COLLECTING_DETAILS
        
        # Default: go back one state or greeting
        previous = self.get_previous_state(current_state)
        return previous if previous else BookingState.GREETING
    
    def get_state_description(self, state: BookingState) -> str:
        """
        Get human-readable description of state
        
        Args:
            state: State to describe
            
        Returns:
            Description string
        """
        descriptions = {
            BookingState.GREETING: "Initial greeting and intent detection",
            BookingState.INFO_MODE: "Providing information to user",
            BookingState.SELECTING_SERVICE: "User selecting service type",
            BookingState.SELECTING_PACKAGE: "User selecting package",
            BookingState.COLLECTING_DETAILS: "Collecting user details (name, email, phone, etc.)",
            BookingState.CONFIRMING: "User confirming booking details",
            BookingState.OTP_SENT: "OTP sent, waiting for verification",
            BookingState.COMPLETED: "Booking completed successfully"
        }
        
        return descriptions.get(state, f"Unknown state: {state}")
    
    def get_state_progress(self, state: BookingState) -> float:
        """
        Get booking progress percentage for current state
        
        Args:
            state: Current state
            
        Returns:
            Progress as percentage (0.0-1.0)
        """
        progress_map = {
            BookingState.GREETING: 0.0,
            BookingState.INFO_MODE: 0.0,
            BookingState.SELECTING_SERVICE: 0.2,
            BookingState.SELECTING_PACKAGE: 0.4,
            BookingState.COLLECTING_DETAILS: 0.6,
            BookingState.CONFIRMING: 0.8,
            BookingState.OTP_SENT: 0.9,
            BookingState.COMPLETED: 1.0
        }
        
        return progress_map.get(state, 0.0)
    
    def get_transition_graph(self) -> Dict[str, List[str]]:
        """
        Get state transition graph as dict for visualization
        
        Returns:
            Dict mapping state names to list of next state names
        """
        graph = {}
        for from_state, to_states in self.transitions.items():
            graph[from_state.value] = [s.value for s in to_states]
        return graph
    
    def validate_transition_path(self, path: List[BookingState]) -> bool:
        """
        Validate if a sequence of state transitions is valid
        
        Args:
            path: List of states representing a path
            
        Returns:
            True if path is valid, False otherwise
        """
        if not path or len(path) < 2:
            return True
        
        for i in range(len(path) - 1):
            if not self.can_transition(path[i], path[i + 1]):
                return False
        
        return True