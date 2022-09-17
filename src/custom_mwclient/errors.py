from mwclient.errors import AssertUserFailedError


class InvalidUserFile(KeyError):
    pass


class RetriedLoginAndStillFailed(AssertUserFailedError):
    def __init__(self, action):
        self.action = action

    def __str__(self):
        return "Tried to re-login but still failed. Attempted action: {}".format(self.action)


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
