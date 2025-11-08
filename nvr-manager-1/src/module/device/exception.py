from base.exception import NVRManagerError


class DeviceNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(700, msg)

class DeviceCaptureFailed(NVRManagerError):
    def __init__(self, msg):
        super().__init__(701, msg)
