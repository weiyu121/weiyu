from base.exception import NVRManagerError


class DVRPlaybackGettingError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(400, msg)

class DVRPlaybackNotExistsError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(401, msg)
