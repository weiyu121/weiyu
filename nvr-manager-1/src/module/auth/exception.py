from base.exception import NVRManagerError


class UserNotLogin(NVRManagerError):
    def __init__(self, msg):
        super().__init__(900, msg)

class UserNotSetPassword(NVRManagerError):
    def __init__(self, msg):
        super().__init__(901, msg)

class UserSetPasswordFailed(NVRManagerError):
    def __init__(self, msg):
        super().__init__(902, msg)

class UserLoginFailed(NVRManagerError):
    def __init__(self, msg):
        super().__init__(903, msg)

class UserAlreadyLogin(NVRManagerError):
    def __init__(self, msg):
        super().__init__(904, msg)

class AddQuestionFailed(NVRManagerError):
    def __init__(self, msg):
        super().__init__(905, msg)

class QuestionNotFound(NVRManagerError):
    def __init__(self, msg):
        super().__init__(906, msg)