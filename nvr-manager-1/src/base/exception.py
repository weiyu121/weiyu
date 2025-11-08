class NVRManagerError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg

class SystemInternalError(NVRManagerError):
    def __init__(self, msg):
        super().__init__(-1, msg)