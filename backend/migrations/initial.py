from sqlalchemy import inspect, text
from src.config.database import Base, engine, Session
from src import models
def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        columns=[column['name'] for column in inspect(connection).get_columns('jobs')]
        if 'rule_version_id' not in columns:
            connection.execute(text('ALTER TABLE jobs ADD COLUMN rule_version_id INTEGER'))
    from src.services.rules import ensure_baseline
    with Session() as db:
        ensure_baseline(db)
        db.commit()
if __name__=='__main__':migrate()
