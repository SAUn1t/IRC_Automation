from dataclasses import dataclass, field
from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    INPUT_VALIDATED = auto()
    DOCUMENT_FOUND = auto()
    BROWSER_READY = auto()
    AUTHENTICATED = auto()
    CHILD_FOUND = auto()
    CHILD_CONFIRMED = auto()
    FORM_REQUESTED = auto()
    FORM_OPEN_CONFIRMED = auto()
    DOCUMENT_PARSED = auto()
    FORM_POPULATED = auto()
    FORM_VERIFIED = auto()
    MANUAL_REVIEW = auto()
    READY_TO_SUBMIT = auto()
    SUBMITTING = auto()
    SUBMISSION_CONFIRMED = auto()
    COMPLETED = auto()
    ERROR = auto()


_ORDER = [state for state in State if state not in (State.MANUAL_REVIEW, State.ERROR)]


@dataclass
class StateMachine:
    current: State = State.IDLE
    history: list[State] = field(default_factory=lambda: [State.IDLE])

    def advance(self, next_state: State) -> None:
        if next_state is State.ERROR:
            if self.current in (State.COMPLETED, State.ERROR):
                raise ValueError("Cannot mark a finished workflow as failed")
        elif next_state is State.MANUAL_REVIEW:
            if self.current is not State.FORM_VERIFIED:
                raise ValueError(f"Invalid transition: {self.current.name} -> {next_state.name}")
        elif self.current is State.ERROR or _ORDER.index(next_state) != _ORDER.index(self.current) + 1:
            raise ValueError(f"Invalid transition: {self.current.name} -> {next_state.name}")
        self.current = next_state
        self.history.append(next_state)
