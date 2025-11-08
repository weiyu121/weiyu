from base.ext import db, BaseModel


@BaseModel.Scope(
    ai_task_args=BaseModel.ScopeType.JSON,
    ai_region=BaseModel.ScopeType.JSON,
    ai_alert_config=BaseModel.ScopeType.JSON,
)
class Device(BaseModel):
    ### @通用字段 ###
    id = db.Column(db.String(30), primary_key=True, nullable=False)
    name = db.Column(db.String(30), nullable=True)

    # 视频流地址
    source = db.Column(db.Text, nullable=False)
    ai_rtmp_stream = db.Column(db.Text, nullable=False)
    ai_http_stream = db.Column(db.Text, nullable=False)
    ai_rtc_stream = db.Column(db.Text, nullable=False)
    stream = db.Column(db.SmallInteger, nullable=True)  # 码流类型：默认码流(0)，主码流(1)、子码流(2)、第三码流(3)...

    # AI项目/任务字段
    ai_project_id = db.Column(db.Integer, nullable=True)  # 可以设外键，但是因为需要对下面两个字段都处理，所以肯定得查表改表，设外键的意义就不大了
    ai_task_enable = db.Column(db.Boolean, nullable=True)  # 启用时，会使用守护线程在其异常关闭后重启
    ai_task_args = db.Column(db.Text, nullable=True)

    # AI多区域
    ai_region = db.Column(db.Text, nullable=True)  # 这个是多区域字段，存成特定的json格式（看接口）【区域必须是2*N个归一化的浮点数表示多边形的区域。传入格式为数组：【x1, y1, x2, y2, ...】，按顺序传入N个点的坐标】

    # AI报警配置
    ai_alert_config = db.Column(db.Text, nullable=True)  # AI报警配置，json格式

    # 云端转发
    enable_forward = db.Column(db.Boolean, nullable=True)  # 是否将原始流转发给云端服务器

    ### @OnVIF摄像头专有字段 ###
    ip = db.Column(db.String(50), nullable=True)
    port = db.Column(db.SMALLINT, nullable=True)
    username = db.Column(db.String(30), nullable=True)
    password = db.Column(db.String(30), nullable=True)

    # 设备信息
    mac = db.Column(db.String(20), nullable=True)
    manufacturer = db.Column(db.String(50), nullable=True)  # 制造商
    model = db.Column(db.String(50), nullable=True)  # 型号
    firmware_version = db.Column(db.String(50), nullable=True)  # 固件版本
    serial_number = db.Column(db.String(50), nullable=True)  # 序列号
    hardware_id = db.Column(db.String(50), nullable=True)  # 序列号

    # ptz
    support_move = db.Column(db.Boolean, nullable=True)  # 支持云台移动
    support_zoom = db.Column(db.Boolean, nullable=True)  # 支持调焦

    ### @海康NVR子摄像头专有字段 ###
    nvr_id = db.Column(db.Integer, db.ForeignKey('hiknvr.id', ondelete='CASCADE'), nullable=True)
    nvr_channel = db.Column(db.SmallInteger, nullable=True)

    def _to_dict_with_filter(self, *extra_scopes: str) -> dict:
        return dict(filter(lambda scope: scope[0] in (
                'id',
                'name',
                'source',
                'ai_rtmp_stream',
                'ai_http_stream',
                'ai_rtc_stream',
                'stream',

                # AI任务相关参数也返回
                'ai_project_id',
                'ai_task_enable',
                'ai_task_args',

                # 转发开启参数
                'enable_forward',
            ) + extra_scopes, self.to_dict().items()))

    def onvif_to_dict(self):
        return self._to_dict_with_filter(
            'ip',
            'port',
            'mac',
            'manufacturer',
            'model',
            'firmware_version',
            'serial_number',
            'hardware_id',
            'support_move',
            'support_zoom',
        )

    def hikcam_to_dict(self):
        return self._to_dict_with_filter(
            'nvr_id',
            'nvr_channel',
        )

    def source_to_dict(self):
        return self._to_dict_with_filter(
            'source',
        )
