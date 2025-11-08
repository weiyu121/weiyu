from base.exception import NVRManagerError


class UpdateSettingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1100, msg)
