from base.exception import NVRManagerError


class HikNVRRegisterError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(500, msg)

class HikNVRNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(501, msg)

class HikNVRCameraAddingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(502, msg)

class HikNVRCameraStreamChangingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(503, msg)

class HikNVRCameraNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(504, msg)
