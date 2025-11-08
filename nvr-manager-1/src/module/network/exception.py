from base.exception import NVRManagerError


class WIFIScanError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1000, msg)

class WIFIConnectError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1001, msg)

class WIFINotConnectError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1002, msg)

class WIFINotAvailable(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1003, msg)

class HotspotNotAvailable(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1010, msg)

class HotspotSetError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1011, msg)

class WireSwitchError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1020, msg)

class MobileNotAvailableError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1030, msg)

class MobileOpenError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(1031, msg)