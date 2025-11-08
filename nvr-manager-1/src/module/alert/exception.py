from base.exception import NVRManagerError


class AlertImageGettingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(200, msg)

class AlertImageNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(201, msg)

class AlertCollectingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(202, msg)

class AlertNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(203, msg)

class AlertRecordNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(204, msg)

class AlertRecordGettingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(205, msg)

class AlertSettingUpdatingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(206, msg)

class AlertCountGettingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(207, msg)