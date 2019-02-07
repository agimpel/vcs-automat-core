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

class VCS_ID(IdProvider):

    orgname = "VCS"

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of id-vcs. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'id-vcs'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        # read config
        self.read_cfg(os.path.join(CFG, "vcs.cfg"))

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def auth(self, rfid):
        try:
            response = self.send_post_request({"rfid":rfid}, self.auth_url)
            if response is False:
                self.logger.info("RFID was unknown")
                return None
            else:
                self.logger.info("RFID was known and data was received")
                return User(rfid = response['rfid'], credits = response['credits'], uid = response['uid'])
        except Exception as e:
            self.logger.exception("auth exception")
            return None

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, rfid, slot):
        try:
            response = self.send_post_request({"rfid":rfid, "slot":slot}, self.report_url)
            if response is False:
                self.logger.critical("CRITICAL: Reporting was unsuccessful of rfid " + str(rfid) + " and slot " + str(slot))
                return False
            else:
                self.logger.info("RFID was known and successfully reported")
                return True
        except Exception as e:
            self.logger.exception("report exception")
            return False



    def info(self):
        try:
            response = self.send_post_request(None, self.info_url)
            if response is False:
                self.logger.critical("CRITICAL: Info was unsuccessful.")
                return False
            else:
                self.logger.debug("Info data was received.")
                return response
        except Exception as e:
            self.logger.exception("info exception")
            return False







    # name
    # INFO:
    # ARGS:     data -> (dict) body of the POST request, url -> (string) target URL for POST request
    # RETURNS:
    def send_post_request(self, data, url):
        if data is None: data = {}
        data['timestamp'] = int(time.time());
        data['nonce'] = binascii.hexlify(os.urandom(10)).decode()+str(int(time.time()));
        body = json.dumps(data).encode('utf8')
        headers = {'X-SIGNATURE': hmac.new(self.api_secret, body, hashlib.sha512).hexdigest(), 'Content-Type': 'application/json'}
        req = urllib.request.Request(url, data = body, headers = headers)

        try:
            resp = urllib.request.urlopen(req)
            http_code = resp.getcode()
            self.logger.info("API responded with status " + str(http_code))
            if http_code is not 200: 
                self.logger.info("This success status code is not implemented.")
                return False
            else:
                resp_raw = resp.read()
                resp_json = json.loads(resp_raw.decode('utf8'))
                if (self.verify_signature(resp.getheader('X-SIGNATURE'), resp_raw) and self.verify_timestamp(resp_json['timestamp']) and self.verify_nonce(resp_json['nonce'])):
                    self.logger.info("Verification of response successful.")
                    return resp_json
                else:
                    self.logger.error("Verification of response failed.")
                    return False
            
        except urllib.error.HTTPError as e:
            http_code = e.code
            self.logger.info("API responded with status " + str(http_code) + ", dismissing")
            return False
        except Exception as e:
            self.logger.exception("Unexpected exception")
            return False
        








    def verify_signature(self, signature, body):
        self.logger.info("Request has signature: "+signature)
        target_signature = hmac.new(self.api_secret, body, hashlib.sha512).hexdigest()
        if (hmac.compare_digest(target_signature, signature)):
            self.logger.info("Signatures match. Verification of signature successful.")
            return True
        else:
            self.logger.info("Signatures do not match. Verification of signature failed.")
            return False

    
    def verify_timestamp(self, timestamp):
        timedelta = 30 #sec
        self.logger.info("Request has timestamp: "+str(timestamp))
        if (timestamp < time.time() + timedelta and timestamp > time.time() - timedelta):
            self.logger.info('Timestamp is within acceptance interval. Verification of timestamp successful.')
            return True
        else:
            self.logger.info('Timestamp is not within acceptance interval. Verification of timestamp failed.')
            return False



    def verify_nonce(self, nonce):
        self.logger.info('Request has nonce: '+str(nonce))
        db_connector = sqlite3.connect(os.path.join(DB, "vcs_nonces.db"))
        db = db_connector.cursor()
        db.execute('SELECT * FROM nonces WHERE nonce = ?', (nonce,))
        if (db.fetchone() == None):
            db.execute("INSERT INTO nonces (nonce, timestamp) VALUES (?, ?)", (str(nonce), str(int(time.time()))))
            db_connector.commit()
            self.logger.info("Nonce was unknown. Verification of nonce successful.")
            db_connector.close()
            return True
        else:
            self.logger.info("Nonce was known. Verification of nonce failed.")
            db_connector.close()
            return False




    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def read_cfg(self, cfg_path):
        config = configparser.SafeConfigParser()
        config.read(cfg_path)
        self.api_secret = bytearray(config['api']['secret'], 'utf8')
        self.auth_url = str(config['api']['auth_url'])
        self.report_url = str(config['api']['report_url'])
        self.info_url = str(config['api']['info_url'])



# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    pass
