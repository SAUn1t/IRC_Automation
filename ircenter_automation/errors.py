class WorkflowError(Exception):
    """A condition requiring the workflow to stop without submitting."""


class ConfigurationError(WorkflowError):
    pass


class DocumentNotFound(WorkflowError):
    pass


class MultipleDocumentsFound(WorkflowError):
    pass


class DocumentParsingError(WorkflowError):
    pass


class AuthenticationRequired(WorkflowError):
    pass


class ChildNotFound(WorkflowError):
    pass


class MultipleChildrenFound(WorkflowError):
    pass


class ChildIdentityMismatch(WorkflowError):
    pass


class FormButtonNotFound(WorkflowError):
    pass


class FormNotOpened(WorkflowError):
    pass


class FieldNotFound(WorkflowError):
    pass


class FieldPopulationError(WorkflowError):
    pass


class VerificationError(WorkflowError):
    pass


class SubmissionError(WorkflowError):
    pass


class SubmissionNotConfirmed(WorkflowError):
    pass


class Stopped(WorkflowError):
    pass
