from base.ext import db, BaseModel


class HikNVR(BaseModel):
    __tablename__ = "hiknvr"
    
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    ip = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(30), nullable=True)
    password = db.Column(db.String(30), nullable=True)
    name = db.Column(db.String(30), nullable=True)
    
    model = db.Column(db.String(50), nullable=True)  # 型号
