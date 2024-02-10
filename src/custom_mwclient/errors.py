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
