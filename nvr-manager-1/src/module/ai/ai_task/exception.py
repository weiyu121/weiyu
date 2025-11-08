from base.exception import NVRManagerError


class AITaskAlreadyRunnigError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(300, msg)

class AITaskNotRunnigError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(301, msg)

class AITaskLaunchError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(302, msg)

class SetAITaskRegionError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(303, msg)

class GetAITaskRegionError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(304, msg)

class SetAITaskAlertError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(305, msg)
