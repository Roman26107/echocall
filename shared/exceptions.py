class CallError(Exception):
    code = 'call_error'
    message = 'Call error'

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class ActiveCallExistsError(CallError):
    code = 'active_call_exists'
    message = 'Active call already exists'

    def __init__(self, call=None, users=None):
        self.call = call
        self.users = users or []
        super().__init__()


class CallNotFoundError(CallError):
    code = 'call_not_found'
    message = 'Call not found'


class InvalidCallTokenError(CallError):
    code = 'invalid_call_token'
    message = 'Invalid call token'


class ParticipantNotFoundError(CallError):
    code = 'participant_not_found'
    message = 'Participant not found'


class IncomingCallForbiddenError(CallError):
    code = 'incoming_call_forbidden'
    message = 'User does not accept incoming calls from you'
