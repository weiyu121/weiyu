from base.exception import NVRManagerError


class IOTDeviceDriverCodeError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1200, msg)
