from mwclient.errors import AssertUserFailedError


class InvalidUserFile(KeyError):
    pass


class RetriedLoginAndStillFailed(AssertUserFailedError):
    def __init__(self, action):
        self.action = action

    def __str__(self):
        return "Tried to re-login but still failed. Attempted action: {}".format(self.action)


class ApiContinueError(Exception):
    """Raised when an exception occurs during an api_continue call."""
    def __init__(self, loop_index: int, action: str, parameters: dict):
        self.loop_index = loop_index
        self.action = action
        self.parameters = parameters

    def __str__(self):
        return (
            f"Error during api_continue call at index {self.loop_index}. "
            f'Action was "{self.action}", parameters were {self.parameters}.'
        )


class ErrorDuringScriptExecution(BaseException):
    """
    To be raised when a fatal error occurs during script execution that causes the script to terminate.
    """
    pass


class ScriptExecutionInvalid(BaseException):
    """
    To be raised when the execution of the script becomes invalid while it is still running.
    """
    pass


class ScriptExecutionKilledByPill(BaseException):
    """
    To be raised when the execution of the script is terminated via pill2kill.
    """
    pass
