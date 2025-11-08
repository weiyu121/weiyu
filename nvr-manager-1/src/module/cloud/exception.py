from base.exception import NVRManagerError


class FowardError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(600, msg)

class FowardAlreadyEnabled(NVRManagerError):
    def __init__(self, msg):
        super().__init__(601, msg)
