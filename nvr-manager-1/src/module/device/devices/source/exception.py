from base.exception import NVRManagerError


class SourceRegisterError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1300, msg)

class SourceNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1301, msg)
