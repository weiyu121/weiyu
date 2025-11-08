from base.exception import NVRManagerError


class AIProjectNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(350, msg)

class AIProjectCreatingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(351, msg)

class AIProjectDeletingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(352, msg)

class AIProjectUpdatingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(353, msg)

class AIProjectModelUpdatingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(354, msg)

class AIProjectOfDefaultNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(355, msg)

class AIProjectSettingUpdatingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(356, msg)