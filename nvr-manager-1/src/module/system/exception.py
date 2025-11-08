from base.exception import NVRManagerError


class SystemInUpgrading(NVRManagerError):
    def __init__(self, msg):
        super().__init__(800, msg)

class SetSystemTimeError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(801, msg)

class SystemUpgradeCheckError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(802, msg)

class SystemAlreadyUptodate(NVRManagerError):
    def __init__(self, msg):
        super().__init__(803, msg)

class SystemGetUpgradeLog(NVRManagerError):
    def __init__(self, msg):
        super().__init__(804, msg)
