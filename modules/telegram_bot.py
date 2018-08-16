from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
import os.path
import logging
import time
from threading import Thread
import sqlite3
from functools import wraps
import configparser
import time


from modules import CFG, DB
from connectors.vcs import VCS_ID



class Telegram_Bot(Thread):

    # in order to prevent massive amounts of requests to the api server, cache results of previous api calls for maxage
    api_information = {'last_reset': None, 'next_reset': None, 'standard_credits': None, 'reset_interval': None, 'last_update': 0}
    api_information_maxage = 60 #s
    rfid_data = {'default': {'credits': 0, 'timestamp': 0}}
    rfid_data_maxage = 5 #s


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


        # conversation handlers
        report_handler = ConversationHandler(
            entry_points = [RegexHandler('(Problem melden)', self.report_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.report_text)],
            },
            fallbacks = [CommandHandler('cancel', self.report_cancel)]
        )
        self.tbot_dp.add_handler(report_handler)

        credits_handler = ConversationHandler(
            entry_points = [RegexHandler('(Guthaben überprüfen)', self.credits_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.credits_setrfid)],
            },
            fallbacks = [CommandHandler('cancel', self.credits_cancel)]
        )
        self.tbot_dp.add_handler(credits_handler)


        # general commands
        self.tbot_dp.add_handler(CommandHandler("start", self.on_start))
        self.tbot_dp.add_handler(RegexHandler("(Hilfe)", self.help))
        self.tbot_dp.add_handler(RegexHandler("(Füllstand überprüfen)", self.check_fill_status))
        self.tbot_dp.add_handler(RegexHandler("(Allgemeine Informationen anzeigen)", self.get_api_info))

        # admin only commands
        self.tbot_dp.add_handler(CommandHandler("ban", self.ban_userid, pass_args=True))
        self.tbot_dp.add_handler(CommandHandler("fillstatus", self.change_fillstatus, pass_args=True))

        # log all errors
        self.tbot_dp.add_error_handler(self.error)

        # start telegram bot
        self.tbot_up.start_polling()

        # signal startup is finished
        self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-Bot Thread wurde gestartet.', disable_notification=True)

        while self.is_running:
            time.sleep(0.05)


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
        self.logger.info('api key and admin group id loaded')


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

        db.execute('SELECT * FROM users')
        self.users_rfid = [[item[0], item[1]] for item in db.fetchall()]

        db_connector.close()
        self.logger.info('admin user ids and blacklist loaded')


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
    def default_keyboard(self):
        keyboard = [['Allgemeine Informationen anzeigen'],['Guthaben überprüfen', 'Füllstand überprüfen'], ['Problem melden', 'Hilfe']]
        return ReplyKeyboardMarkup(keyboard)


    def default_state(self, bot, update):
        update.message.reply_text('Was kann ich für dich tun?', reply_markup = self.default_keyboard())





    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def get_name(self, update):
        name = ''
        if update.message.from_user.first_name:
            name += update.message.from_user.first_name
        if update.message.from_user.last_name:
            if name is not '':
                name += ' '
            name += update.message.from_user.last_name
        return name

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def get_helptext(self, update):
        output = 'Hier ist was ich kann:\n'
        output += '\nHilfe: Zeigt die Befehle'
        output += '\nFüllstand überprüfen: Gibt den Füllstand des Automaten'
        output += '\nProblem melden: Leitet eine Meldung an die Verantwortlichen weiter'

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
        self.default_state(bot, update)


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def check_fill_status(self, bot, update):
        update.message.reply_text('🤖')
        self.default_state(bot, update)



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def get_api_info(self, bot, update):
        if time.time() > self.api_information['last_update'] + self.api_information_maxage:
            conn = VCS_ID()
            data = conn.info()
            for setting in ['last_reset', 'next_reset', 'standard_credits', 'reset_interval']:
                if setting in data: 
                    self.api_information[setting] = data[setting]
                else:
                    self.api_information[setting] = None
                self.api_information['last_update'] = time.time()

        update.message.reply_text('Das Guthaben wird am '+time.strftime('%d.%m, %H', time.localtime(int(self.api_information['next_reset'])))+' Uhr erneuert.\n\nMomentan steht alle '+self.api_information['reset_interval']+' Tage ein Guthaben von '+self.api_information['standard_credits']+' Freigetränk(en) zur Verfügung. Zuletzt wurde das Guthaben am '+time.strftime('%d.%m, %H', time.localtime(int(self.api_information['last_reset'])))+' Uhr erneuert.')
        self.default_state(bot, update)




    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report_entry(self, bot, update):
        if update.message.from_user.id not in self.blacklist_user_id:
            update.message.reply_text('Hiermit wirst du eine Meldung an die Administratoren des Bierautomaten senden. Übermässige oder unsachgemässe Verwendung führt dazu, dass du gesperrt wirst.\n\nBitte sende mir deine Meldung als Nachricht oder breche den Vorgang mit /cancel ab:', reply_markup = ReplyKeyboardRemove())
            return 1
        else:
            update.message.reply_text('Du darfst keine Meldungen mehr einreichen.\nHälst du das für einen Fehler, melde dich bei bierko@vcs.ethz.ch', reply_markup = ReplyKeyboardRemove())
            self.default_state(bot, update)
            return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report_text(self, bot, update):
        update.message.reply_text('Deine Meldung wurde übermittelt!', reply_markup = ReplyKeyboardRemove())
        bot.send_message(chat_id=self.admin_group_id, text='Meldung\n--------------\nvon {}\nID {}\num {}\n\n {}'.format(self.get_name(update), update.effective_user.id, update.message.date, update.message.text), disable_notification=True)
        self.default_state(bot, update)
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report_cancel(self, bot, update):
        update.message.reply_text('Vorgang abgebrochen.', reply_markup = ReplyKeyboardRemove())
        self.default_state(bot, update)
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def credits_entry(self, bot, update):
        # check if user has associated rfid, if not: present rfid submission dialogue, if yes: print remaining credits based on connectors
        if update.effective_user.id not in [user[0] for user in self.users_rfid]:
            update.message.reply_text('Um dein Guthaben abzurufen muss deine Legi-Identifikationsnummer mit deinem Telegram-Account in Verbindung gebracht werden. Ich werde mir die Legi-Identifikationsnummer merken und künftig direkt mit deinem Guthaben antworten.\n\nBitte sende mir deine Legi-Identifikationsnummer als Nachricht oder breche den Vorgang mit /cancel ab:', reply_markup = ReplyKeyboardRemove())
            return 1
        rfid = self.users_rfid[update.effective_user.id][1]
        if rfid in self.rfid_data and time.time() < self.rfid_data[rfid]['timestamp'] + self.rfid_data_maxage:
            remaining_credits = self.rfid_data[rfid]['credits']
        else:
            conn = VCS_ID()
            data = conn.auth(rfid)
            if data is False:
                update.message.reply_text('Deine RFID ist unbekannt oder ein Fehler ist aufgetreten.')
                self.default_state(bot, update)
                return ConversationHandler.END
            remaining_credits = data.credits
            update.message.reply_text('Dein Guthaben beträgt '+str(remaining_credits)+' Freigetränk(e).')
            self.default_state(bot, update)
        return ConversationHandler.END

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def credits_setrfid(self, bot, update):
        # present rfid submission dialogue, add /cancel info
        # ensure sanitisation!
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def credits_cancel(self, bot, update):
        update.message.reply_text('Vorgang abgebrochen.', reply_markup = ReplyKeyboardRemove())
        self.default_state(bot, update)
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def help(self, bot, update):
        update.message.reply_text(self.get_helptext(update))
        self.default_state(bot, update)

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
        self.default_state(bot, update)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_userid(self, bot, update, args):
        update.message.reply_text('User ID {} wurde geblockt!'.format(args))
        self.default_state(bot, update)


# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    print('Hi')
