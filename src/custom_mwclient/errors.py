from mwclient.errors import AssertUserFailedError


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
