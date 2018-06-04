import logging
import os.path
import logging
from connectors import User, IdProvider
from modules import CFG, DB
import configparser
import urllib.parse, urllib.request, urllib.error
import json
import hashlib
import hmac


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
            (http_code, response) = self.send_post_request({"rfid":rfid}, self.auth_url)
            if http_code == 404:
                self.logger.info("RFID was unknown")
                return False
            elif http_code == 200 and response is not None:
                self.logger.info("RFID was known and data was received")
                return User(rfid = response['rfid'], credits = response['credits'], nethz = response['nethz'], name = 'Max Muster')
            else:
                self.logger.error("Received unexpected response with status code " + str(http_code))
                return False
        except Exception as e:
            self.logger.exception("auth exception")
            return False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, rfid, slot):
        try:
            (http_code, _) = self.send_post_request({"rfid":rfid, "slot":slot}, self.report_url)
            if http_code == 500:
                self.logger.critical("CRITICAL: Reporting was unsuccessfull of rfid " + rfid + " and slot " + slot)
                return False
            elif http_code == 201:
                self.logger.info("RFID was known and successfully reported")
                return True
            else:
                self.logger.critical("CRITICAL: Received unexpected response with status code " + str(http_code) + " upon request with rfid " + rfid + " and slot " + slot)
                return False
        except Exception as e:
            self.logger.exception("report exception")
            return False


    # name
    # INFO:
    # ARGS:     data -> (dict) body of the POST request, url -> (string) target URL for POST request
    # RETURNS:
    def send_post_request(self, data, url):
        body = json.dumps(data).encode('utf8')
        headers = {'X-SIGNATURE': hmac.new(self.api_secret, body, hashlib.sha512).hexdigest(), 'Content-Type': 'application/json'}
        req = urllib.request.Request(url, data = body, headers = headers)

        try:
            resp = urllib.request.urlopen(req)
            http_code = resp.getcode()
            if http_code == 200: 
                resp = json.loads(resp.read().decode('utf-8'))
            else:
                resp = False
            self.logger.info("API responded with status " + str(http_code))
        except urllib.error.HTTPError as e:
            resp = False
            http_code = e.code
            self.logger.info("API responded with status " + str(http_code))
        except Exception as e:
            self.logger.exception("catched exception")
            resp = False
            http_code = None
        
        return (http_code, resp)





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
