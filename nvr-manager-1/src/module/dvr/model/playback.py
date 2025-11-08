from base.ext import db, BaseModel


@BaseModel.Scope(
    event_time=BaseModel.ScopeType.DATETIME
)
class Playback(BaseModel):
    id = db.Column(db.Integer(), primary_key=True, nullable=False)  # 主键
    file_path = db.Column(db.String(200), nullable=False)  # 文件路径
    event_time = db.Column(db.DateTime(timezone=True), nullable=False)  # 录制发生时间
    device_id = db.Column(db.String(30), nullable=False)  # 设备id
    device_name = db.Column(db.String(30), nullable=False)  # 设备名称
    duration = db.Column(db.SmallInteger(), nullable=False)  # 时长/秒

    def _get_scope_type(self):
        return {
            'event_time': self.ScopeType.DATETIME
        }