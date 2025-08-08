from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# SQLAlchemy instance (will be initialized with app in app.py)
db = SQLAlchemy()

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.String, primary_key=True)
    filename = db.Column(db.String, nullable=True)
    status = db.Column(db.String, nullable=False, default='PENDING')
    progress = db.Column(db.Integer, nullable=False, default=0)
    status_message = db.Column(db.String, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    transcript = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'status': self.status,
            'progress': self.progress,
            'status_message': self.status_message,
            'summary': self.summary,
            'transcript': self.transcript,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

class Setting(db.Model):
    __tablename__ = 'settings'
    key = db.Column(db.String, primary_key=True)
    value = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(key, default=None):
        s = Setting.query.get(key)
        return s.value if s else default

    @staticmethod
    def set(key, value):
        s = Setting.query.get(key)
        if not s:
            s = Setting(key=key, value=value)
            db.session.add(s)
        else:
            s.value = value
        db.session.commit()
