from telegram.ext import Updater, CommandHandler
import os.path
import logging
import time
from threading import Thread
import sqlite3
from functools import wraps
import configparser


from modules import CFG, DB


class Telegram_Bot(Thread):

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of tbot. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'tbot'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        self.admin_user_id = []
        self.blacklist_user_id = []

        self.read_cfg(os.path.join(CFG, "tbot.cfg"))
        self.initialise_db(os.path.join(DB, "tbot.db"))

        Thread.__init__(self, daemon=True)
        self.is_running = False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def run(self):
        self.is_running = True

        self.tbot_up = Updater(self.telegram_api_key)
        self.tbot_dp = self.tbot_up.dispatcher
        self.tbot_jq = self.tbot_up.job_queue

        # general commands
        self.tbot_dp.add_handler(CommandHandler("start", self.on_start))
        self.tbot_dp.add_handler(CommandHandler("report", self.report, pass_args=True))
        self.tbot_dp.add_handler(CommandHandler("help", self.help))
        self.tbot_dp.add_handler(CommandHandler("status", self.check_fill_status))
        self.tbot_dp.add_handler(CommandHandler("puls", self.check_responsiveness))

        # admin only commands
        self.tbot_dp.add_handler(CommandHandler("ban", self.ban_userid, pass_args=True))
        self.tbot_dp.add_handler(CommandHandler("fillstatus", self.change_fillstatus, pass_args=True))

        # log all errors0
        self.tbot_dp.add_error_handler(self.error)

        # start telegram bot
        self.tbot_up.start_polling()

        while self.is_running:
            time.sleep(0.2)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def read_cfg(self, cfg_path):
        config = configparser.SafeConfigParser()
        config.read(cfg_path)
        self.telegram_api_key = str(config['telegram']['api_key'])
        self.admin_group_id = int(config['telegram']['admin_group_id'])

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def initialise_db(self, db_path):
        db_connector = sqlite3.connect(db_path)
        db = db_connector.cursor()

        db.execute('SELECT * FROM admins')
        self.admin_user_id = [item[0] for item in db.fetchall()]

        db.execute('SELECT * FROM blacklist')
        self.blacklist_user_id = [item[0] for item in db.fetchall()]

        db_connector.close()

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def admin_only(func):
        @wraps(func)
        def wrapped(self, bot, update, *args, **kwargs):
            user_id = update.effective_user.id
            if user_id not in self.admin_user_id:
                self.logger.warning("Unauthorized access denied for {}.".format(user_id))
                return
            return func(self, bot, update, *args, **kwargs)
        return wrapped

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def get_name(self, update):
        name = ''
        if update.message.from_user.first_name:
            name += update.message.from_user.first_name
        if update.message.from_user.last_name:
            name += ' '
            name += update.message.from_user.last_name
        return name

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def get_helptext(self, update):
        output = 'Hier ist was ich kann:\n'
        output += '\n/help Zeigt die Befehle'
        output += '\n/status Gibt den Füllstand des Automaten'
        output += '\n/puls Überprüft Bot auf Lebenszeichen'
        output += '\n/report <Meldung> Leitet eine Meldung an die Verantwortlichen weiter'

        user_id = update.effective_user.id
        if user_id in self.admin_user_id:
            output += '\n\nWeitere Befehle für Admins:'
            output += '\n/fillstatus <Zahl> Aktualisiert den Füllstand des Automaten auf <Zahl>'
            output += '\n/ban <ID> Blockt Meldungen von User mit dieser ID'

        return output

    #
    # COMMAND HANDLERS
    #

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def on_start(self, bot, update):
        name = self.get_name(update)
        help_text = self.get_helptext(update)
        update.message.reply_text('Hallo {}!\nIch bin ein Bot für den VCS-Bierautomaten. Bei Fragen & Feedback wende dich an bierko@vcs.ethz.ch.\n{}'.format(name, help_text))

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def check_responsiveness(self, bot, update):
        update.message.reply_text('🤖')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def check_fill_status(self, bot, update):
        update.message.reply_text('🤖')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, bot, update, args):
        if update.message.from_user.id not in self.blacklist_user_id:
            update.message.reply_text('Deine Meldung wurde übermittelt!')
            name = self.get_name(update)

            bot.send_message(chat_id=self.admin_group_id, text='Meldung\n--------------\nvon {}\nID {}\num {}\n\n {}'.format(name, update.effective_user.id, update.message.date, ' '.join(args)), disable_notification=True)
        else:
            update.message.reply_text('Du darfst keine Meldungen mehr einreichen.\nHälst du das für einen Fehler, melde dich bei bierko@vcs.ethz.ch')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def help(self, bot, update):
        update.message.reply_text(self.get_helptext(update))

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def error(self, bot, update, error):
        self.logger.warning('Update "%s" caused error "%s"', update, error)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def change_fillstatus(self, bot, update, args):
        update.message.reply_text('To be implemented!')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_userid(self, bot, update, args):
        update.message.reply_text('User ID {} wurde geblockt!'.format(args))


# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    print('Hi')
