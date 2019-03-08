import logging
import os.path
import os
import logging
from connectors import User, IdProvider
from modules import CFG, DB
import configparser
import urllib.parse, urllib.request, urllib.error
import json
import hashlib
import hmac
import time
import binascii
import sqlite3


class DB_ID(IdProvider):

    orgname = "DB"

    db_path = os.path.join(DB, "users.db")

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of id-db. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'id-db'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def auth(self, rfid):

        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute('SELECT * FROM users')
        users = [item[0] for item in db.fetchall()]

        db_connector.close()

        if str(rfid) in users:
            self.logger.info('Found rfid %s in the database for special access.' % str(rfid))
            return User(rfid = int(rfid), credits = 69, uid = 'Database Entry')
        else:
            return None


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, rfid, slot):
        try:
            db_connector = sqlite3.connect(self.db_path)
            db = db_connector.cursor()
            db.execute('UPDATE users SET usage = usage + 1 WHERE rfid = %s' % str(rfid))
            db_connector.commit()
            db_connector.close()
            return True
        except Exception as e:
            self.logger.exception("report exception: " + e)
            return False
