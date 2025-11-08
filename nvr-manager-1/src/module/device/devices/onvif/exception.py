from base.exception import NVRManagerError


class OnvifRegisterError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(100, msg)

class OnvifExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(101, msg)

class OnvifNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(102, msg)

class OnvifOfflineError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(103, msg)

class OnvifStreamChangingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(104, msg)

    