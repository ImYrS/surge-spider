from os import path

from peewee import SqliteDatabase, Model, PrimaryKeyField, CharField, IntegerField, BigIntegerField, TextField
from configobj import ConfigObj

config = ConfigObj('config.ini', encoding='utf8')
db = SqliteDatabase(config['db']['path'])


class BaseModel(Model):
    class Meta:
        database = db


class Release(BaseModel):
    id = PrimaryKeyField()
    version = IntegerField(unique=True)
    tag = CharField()
    description = TextField(null=True)
    url = TextField()
    filename = CharField(null=True)
    created_at = BigIntegerField()


def init_db():
    if path.exists(config['db']['path']):
        return

    db.connect()
    db.create_tables([Release])
    db.close()
