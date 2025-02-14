from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import pytz

db = SQLAlchemy()

def get_china_time():
    return datetime.now(pytz.timezone('Asia/Shanghai'))

class TestSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_time = db.Column(db.DateTime, default=get_china_time)
    prompt = db.Column(db.Text)
    # 一个测试会话包含多个测试记录
    records = db.relationship('TestRecord', backref='session', lazy=True)

class TestRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_session.id'), nullable=False)
    provider = db.Column(db.String(100))
    first_token_time = db.Column(db.Float)
    reasoning_speed = db.Column(db.Float)
    content_speed = db.Column(db.Float)
    average_speed = db.Column(db.Float)
    log_content = db.Column(db.Text)
    error = db.Column(db.Text) 