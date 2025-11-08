from base.ext import db, BaseModel


@BaseModel.Scope(
    information=BaseModel.ScopeType.JSON,
    time=BaseModel.ScopeType.DATETIME
)
class Alert(BaseModel):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True, nullable=False)
    object = db.Column(db.String(30), nullable=False)
    event = db.Column(db.String(30), nullable=False)
    region = db.Column(db.String(30), nullable=True)
    information = db.Column(db.Text, nullable=True)

    time = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.text('NOW()'))
    device_id = db.Column(db.String(30), nullable=False)
    device_name = db.Column(db.String(30), nullable=False)
    image_path = db.Column(db.String(200), nullable=True)
    record_path = db.Column(db.String(200), nullable=True)
