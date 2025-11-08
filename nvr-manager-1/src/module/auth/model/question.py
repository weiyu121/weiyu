from base.ext import db, BaseModel


class Question(BaseModel):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True, nullable=False)
    question = db.Column(db.String(20), nullable=False)
    answer = db.Column(db.String(40), nullable=False)
