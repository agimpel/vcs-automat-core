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
import re

from modules import CFG, DB
from connectors.vcs import VCS_ID



# Telegram_Bot
# INFO:     Thread of the telegram bot, started from main thread and runs continuously. All handlers and commands are defined within the class.
# ARGS:     /
# RETURNS:  /
class Telegram_Bot(Thread):

    # in order to prevent massive amounts of requests to the api server, cache results of previous api calls for maxage
    api_information = {'last_reset': None, 'next_reset': None, 'standard_credits': None, 'reset_interval': None, 'last_update': 0}
    api_information_maxage = 60 #s
    rfid_data = {'default': {'credits': 0, 'timestamp': 0}}
    rfid_data_maxage = 60 #s

    # lists of telegram ids for admins and blocked users
    admin_user_id = []
    blacklist_user_id = []

    # list of currently available contents in the maschine per slot and maximal loading per slot
    automat_content = {'slot': {'amount': 0, 'max_amount': 0, 'notification_level': 0}}
    max_content_per_slot = 50

    # at which remaining content levels to notify the admin group (relative to maximal amount). Note: at 0, there is always an automatic notification
    notification_content_levels = [0.25, 0.10, 0.05, 0.00] # at 25%, 10%, 5% and 0%

    # define which slots are shown by the telegram bot and define the offset for the shown number (bot will show slot_number - slot_offset)
    active_slots = [3, 4, 5, 6, 7, 8]
    slot_offset = 2

    # __init__
    # INFO:     Sets up logging and paths for config and database files, then reads them and starts the thread (using SQLite3)
    # ARGS:     /
    # RETURNS:  /
    def __init__(self):
        # set-up for logging of tbot. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.INFO
        self.logtitle = 'tbot'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        self.cfg_path = os.path.join(CFG, "tbot.cfg")
        self.db_path = os.path.join(DB, "tbot.db")
        self.read_cfg()
        self.initialise_db()

        Thread.__init__(self, daemon=True)
        self.is_running = False
        self.shutdown = False

    # run
    # INFO:     Main loop of the telegram bot. All handlers for commands are registered here.
    # ARGS:     /
    # RETURNS:  /
    def run(self):
        self.is_running = True

        self.tbot_up = Updater(self.telegram_api_key)
        self.tbot_dp = self.tbot_up.dispatcher
        self.tbot_jq = self.tbot_up.job_queue


        # general conversation handler: Reporting
        report_handler = ConversationHandler(
            entry_points = [RegexHandler('(Problem melden)', self.report_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.report_text)],
            },
            fallbacks = [CommandHandler('cancel', self.report_cancel)]
        )
        self.tbot_dp.add_handler(report_handler)

        # general conversation handler: Credit Check
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

        # admin only conversation handler: Set Amount
        amount_handler = ConversationHandler(
            entry_points = [RegexHandler('(Füllstand ändern)', self.amount_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.amount_get_slot, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.amount_get_amount, pass_user_data=True)],
            },
            fallbacks = [RegexHandler("(Beenden)", self.amount_cancel)]
        )
        self.tbot_dp.add_handler(amount_handler)

        # admin only conversation handler: Set Max-Amount
        maxamount_handler = ConversationHandler(
            entry_points = [RegexHandler('(Maximalmengen ändern)', self.maxamount_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.maxamount_get_slot, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.maxamount_get_amount, pass_user_data=True)],
            },
            fallbacks = [RegexHandler("(Beenden)", self.maxamount_cancel)]
        )
        self.tbot_dp.add_handler(maxamount_handler)

        # admin only conversation handler: Ban User
        ban_handler = ConversationHandler(
            entry_points = [RegexHandler('(User bannen)', self.ban_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.ban_get_id, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.ban_get_confirmation, pass_user_data=True)],
            },
            fallbacks = [RegexHandler("(Beenden)", self.ban_cancel)]
        )
        self.tbot_dp.add_handler(ban_handler)

        # admin only commands
        self.tbot_dp.add_handler(RegexHandler("(Administratives)", self.admin_panel))
        self.tbot_dp.add_handler(RegexHandler("(Datenbanken aktualisieren)", self.reload_databases))
        self.tbot_dp.add_handler(RegexHandler("(Automat neustarten)", self.restart_service))
        self.tbot_dp.add_handler(RegexHandler("(Zurück zur Übersicht)", self.default_state))
        self.tbot_dp.add_handler(CommandHandler("send", self.answer_report, pass_args=True))

        # fallback command
        self.tbot_dp.add_handler(RegexHandler(".*", self.help))

        # log all errors
        self.tbot_dp.add_error_handler(self.error)

        # start telegram bot. This spawns another thread which is responsible for handling the Telegram API. It is terminated upon termination of this thread.
        self.tbot_up.start_polling()

        # signal startup is finished
        # self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-Bot Thread wurde gestartet.', disable_notification=True)

        # keep this thread alive
        while self.is_running:
            time.sleep(1)
        
        # signal shutdown
        self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-Bot Thread wurde gestoppt.', disable_notification=True)

    # exit
    # INFO:     Stops the telegram bot thread.
    # ARGS:     /
    # RETURNS:  /
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False

    # read_cfg
    # INFO:     Reads the configuration file for the telegram bot. Read values are the Telegram API key and the ID of the admin group.
    # ARGS:     /
    # RETURNS:  /
    def read_cfg(self):
        config = configparser.SafeConfigParser()
        config.read(self.cfg_path)
        self.telegram_api_key = str(config['telegram']['api_key'])
        self.admin_group_id = int(config['telegram']['admin_group_id'])
        self.logger.info('config loaded')

    # register_user_in_db
    # INFO:     Saves a relationship between Telegram ID, which is visible to the telegram bot, and RFID, which is necessary for authentication against the VCS API in the database.
    # ARGS:     id -> (string) Telegram ID of user to register the RFID for, rfid -> (string) RFID of the identification card to save
    # RETURNS:  True
    def register_user_in_db(self, id, rfid):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute("INSERT INTO users (ID, rfid) VALUES ('"+str(id)+"','"+str(rfid)+"')")
        db_connector.commit()

        db.execute('SELECT * FROM users')
        self.users_rfid = {item[0]: item[1] for item in db.fetchall()}

        db_connector.close()
        self.logger.info('ID '+str(id)+ ' with RFID '+str(rfid)+' successfully registered in database.')
        return True

    # set_amount_in_db
    # INFO:     Assing a content amount or the maximum available content amount of a slot to save in the database. amount is expected to be within [0, max_amount]
    # ARGS:     slot -> (int) Slot of the automat, amount -> (int) amount to set the slot to, max_amount -> (int) maximum amount to set the slot to
    # RETURNS:  True
    def set_amount_in_db(self, slot, amount = None, max_amount = None):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        if amount is not None:
            db.execute("UPDATE automat SET amount = '"+str(amount)+"' WHERE slot = '"+str(slot)+"'")
            db_connector.commit()
            self.logger.info('Amount in slot '+str(slot)+ ' updated to '+str(amount)+' successfully in database.')

        if max_amount is not None:
            db.execute("UPDATE automat SET max_amount = '"+str(max_amount)+"' WHERE slot = '"+str(slot)+"'")
            db_connector.commit()
            self.logger.info('Max amount in slot '+str(slot)+ ' updated to '+str(max_amount)+' successfully in database.')

        db_connector.close()
        return True

    # ban_user_in_db
    # INFO:
    # ARGS:
    # RETURNS:
    def ban_user_in_db(self, banned_id, id_of_admin = 000000):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute("INSERT INTO blacklist (ID, timestamp, by) VALUES ('"+str(banned_id)+"', '"+str(int(time.time()))+"', '"+str(id_of_admin)+"')")
        db_connector.commit()
        self.logger.info('Telegram ID '+str(banned_id)+ ' was banned by '+str(id_of_admin)+' successfully in database.')

        db_connector.close()
        return True

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def save_report_in_db(self, report_text, id_of_reporter):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute("INSERT INTO reports (ID, timestamp, text) VALUES ('"+str(id_of_reporter)+"', '"+str(int(time.time()))+"', '"+str(report_text)+"')")
        db_connector.commit()
        self.logger.info('Telegram ID '+str(id_of_reporter)+' and its report successfully saved in database.')

        db_connector.close()
        return True
    
    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def initialise_db(self):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute('SELECT * FROM admins')
        self.admin_user_id = [item[0] for item in db.fetchall()]

        db.execute('SELECT * FROM blacklist')
        self.blacklist_user_id = [item[0] for item in db.fetchall()]

        db.execute('SELECT * FROM users')
        self.users_rfid = {item[0]: item[1] for item in db.fetchall()}

        db.execute('SELECT * FROM automat')
        self.automat_content = {item[0]: {'amount': item[1], 'max_amount': item[2], 'notification_level': 0} for item in db.fetchall()}

        db_connector.close()
        self.logger.info('database loaded')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def admin_only(func):
        @wraps(func)
        def wrapped(self, bot, update, *args, **kwargs):
            user_id = str(update.effective_user.id)
            if user_id not in self.admin_user_id:
                self.logger.info("Unauthorized access denied for {}.".format(user_id))
                return self.help(bot, update)
            return func(self, bot, update, *args, **kwargs)
        return wrapped

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def default_keyboard(self):
        keyboard = [['Allgemeine Informationen anzeigen'],['Guthaben überprüfen', 'Füllstand überprüfen'], ['Problem melden', 'Hilfe']]
        return ReplyKeyboardMarkup(keyboard)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def default_keyboard_for_admins(self):
        keyboard = [['Allgemeine Informationen anzeigen'],['Guthaben überprüfen', 'Füllstand überprüfen'], ['Problem melden', 'Hilfe'], ['Administratives']]
        return ReplyKeyboardMarkup(keyboard)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def admin_keyboard(self):
        keyboard = [['Füllstand ändern', 'Maximalmengen ändern'], ['User bannen', 'Datenbanken aktualisieren'], ['Automat neustarten'], ['Zurück zur Übersicht']]
        return ReplyKeyboardMarkup(keyboard)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def slot_keyboard(self, with_complete = False):
        keyboard = [['1', '2', '3'], ['4', '5', '6'], ['Beenden']]
        if with_complete is not False:
            keyboard.insert(2, ['Alles gefüllt'])
        return ReplyKeyboardMarkup(keyboard)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def default_state(self, bot, update):
        if str(update.effective_user.id) in self.admin_user_id:
            update.message.reply_text('Was kann ich für dich tun?', reply_markup = self.default_keyboard_for_admins())
        else:
            update.message.reply_text('Was kann ich für dich tun?', reply_markup = self.default_keyboard())

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def admin_panel(self, bot, update):
        update.message.reply_text('Wähle eine administrative Option:', reply_markup = self.admin_keyboard())

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

        user_id = str(update.effective_user.id)
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
        string = 'Momentaner Füllstand:\n\n'
        for slot, slot_dict in self.automat_content.items():
            if slot in self.active_slots:
                string += 'Slot '+str(slot-self.slot_offset)+': '+str(slot_dict['amount'])+'/'+str(slot_dict['max_amount'])+'\n'
        update.message.reply_text(string)
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
        if str(update.message.from_user.id) not in self.blacklist_user_id:
            update.message.reply_text('Hiermit wirst du eine Meldung an die Administratoren des Bierautomaten senden. Übermässige oder unsachgemässe Verwendung führt dazu, dass du gesperrt wirst.\n\nBitte sende mir deine Meldung als Nachricht oder breche den Vorgang mit /cancel ab:', reply_markup = ReplyKeyboardRemove())
            return 1
        else:
            update.message.reply_text('Du darfst keine Meldungen mehr einreichen.\nHälst du das für einen Fehler, melde dich bei bierko@vcs.ethz.ch')
            self.default_state(bot, update)
            return ConversationHandler.END

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report_text(self, bot, update):
        update.message.reply_text('Deine Meldung wurde übermittelt!', reply_markup = ReplyKeyboardRemove())
        bot.send_message(chat_id=self.admin_group_id, text='Meldung\n--------------\nvon {}\nID {}\num {}\n\n {}\n\nBeantworten mit \\send {} <TEXT>'.format(self.get_name(update), update.effective_user.id, update.message.date, update.message.text, update.effective_user.id), disable_notification=True)
        self.save_report_in_db(update.message.text, update.effective_user.id)
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
        if str(update.effective_user.id) not in self.users_rfid:
            update.message.reply_text('Um dein Guthaben abzurufen muss deine Legi-Identifikationsnummer mit deinem Telegram-Account in Verbindung gebracht werden. Ich werde mir die Legi-Identifikationsnummer merken und künftig direkt mit deinem Guthaben antworten.\n\nBitte sende mir deine Legi-Identifikationsnummer als Nachricht oder breche den Vorgang mit /cancel ab:', reply_markup = ReplyKeyboardRemove())
            return 1
        rfid = self.users_rfid[str(update.effective_user.id)]
        if rfid in self.rfid_data and time.time() < self.rfid_data[rfid]['timestamp'] + self.rfid_data_maxage:
            remaining_credits = self.rfid_data[rfid]['credits']
        else:
            conn = VCS_ID()
            data = conn.auth(rfid)
            if data is None:
                update.message.reply_text('Deine RFID ist unbekannt oder ein Fehler ist aufgetreten.')
                self.logger.error('RFID '+str(rfid)+' was either unknown or there was an error.')
                self.default_state(bot, update)
                return ConversationHandler.END
            remaining_credits = data.credits
        update.message.reply_text('Dein Guthaben beträgt '+str(remaining_credits)+' Freigetränk(e).')
        self.rfid_data[rfid] = {'credits': remaining_credits, 'timestamp': time.time()}
        self.default_state(bot, update)
        return ConversationHandler.END

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def credits_setrfid(self, bot, update):
        raw_rfid = str(update.message.text)
        if re.compile("[^0-9]").match(raw_rfid) is not None:
            self.logger.info('Entered rfid contained non-numeric characters.')
            update.message.reply_text('Die Identifikationsnummer kann nur Zahlen enthalten. Versuche es erneut:')
            return 1
        if len(raw_rfid) is not 6:
            self.logger.info('Entered rfid is not of correct length.')
            update.message.reply_text('Die Identifikationsnummer besteht aus 6 Zahlen. Versuche es erneut:')
            return 1

        self.users_rfid[update.effective_user.id] = raw_rfid
        self.rfid_data[raw_rfid] = {'credits': 0, 'timestamp': 0}
        self.register_user_in_db(update.effective_user.id, raw_rfid)
        update.message.reply_text('Die Identifikationsnummer wurde erfolgreich gespeichert!')
        return self.credits_entry(bot, update)

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
    def amount_entry(self, bot, update):
        update.message.reply_text('Welcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=True))
        return 1

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def amount_get_slot(self, bot, update, user_data):
        slot = str(update.message.text)
        if slot == 'Beenden':
            return self.amount_cancel(bot, update)
        if slot == 'Alles gefüllt':
            update.message.reply_text('Alle Slots auf ihr Maximum aktualisiert.')
            for slot_number in self.automat_content: self.update_fillstatus_callback(slot_number, amount = self.automat_content[slot_number]['max_amount'])
            self.admin_panel(bot, update)
            return ConversationHandler.END

        try:
            slot = int(slot)
        except ValueError:
            update.message.reply_text('Das ist ein ungültiger Slot.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=True))
            return 1
        
        if slot not in self.automat_content:
            update.message.reply_text('Das ist ein ungültiger Slot.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=True))
            return 1
        update.message.reply_text('Auf welche Menge soll der Slot '+str(slot)+' aktualisiert werden?\nSende \'*\' für die Maximalmenge, also '+str(self.automat_content[slot]['max_amount'])+'.', reply_markup = ReplyKeyboardRemove())
        user_data['slot'] = slot
        return 2

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def amount_get_amount(self, bot, update, user_data):
        amount = str(update.message.text)
        if amount == 'Beenden':
            return self.amount_cancel(bot, update)
        if 'slot' not in user_data:
            update.message.reply_text('Kein Slot gesetzt.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=True))
            return 1
        slot = user_data['slot']
        if amount == '*':
            amount = self.automat_content[slot]['max_amount']
            
        try:
            amount = int(amount)
        except ValueError:
            update.message.reply_text('Ungültiger Wert.\nAuf welche Menge soll der Slot '+str(slot)+' aktualisiert werden?\nSende \'*\' für die Maximalmenge, also '+str(self.automat_content[slot]['max_amount'])+'.', reply_markup = ReplyKeyboardRemove())
            return 2
        
        if not (amount >= 0 and amount <= self.automat_content[slot]['max_amount']):
            update.message.reply_text('Ungültiger Wert.\nAuf welche Menge soll der Slot '+str(slot)+' aktualisiert werden?\nSende \'*\' für die Maximalmenge, also '+str(self.automat_content[slot]['max_amount'])+'.', reply_markup = ReplyKeyboardRemove())
            return 2
        user_data.pop('slot')
        self.update_fillstatus_callback(slot, amount = amount)
        update.message.reply_text('Slot '+str(slot)+' erfolgreich auf '+str(amount)+' geändert.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=True))
        return 1

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def amount_cancel(self, bot, update):
        update.message.reply_text('Vorgang beendet.')
        self.admin_panel(bot, update)
        return ConversationHandler.END

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_entry(self, bot, update):
        update.message.reply_text('Für welchen Slot soll die Maximalmenge aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=False))
        return 1

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_get_slot(self, bot, update, user_data):
        slot = str(update.message.text)
        if slot == 'Beenden':
            return self.maxamount_cancel(bot, update)

        try:
            slot = int(slot)
        except ValueError:
            update.message.reply_text('Das ist ein ungültiger Slot.\nFür welchen Slot soll die Maximalmenge aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=False))
            return 1
        
        if slot not in self.automat_content:
            update.message.reply_text('Das ist ein ungültiger Slot.\nFür welchen Slot soll die Maximalmenge aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=False))
            return 1
        update.message.reply_text('Auf welche Maximalmenge soll der Slot '+str(slot)+' aktualisiert werden?', reply_markup = ReplyKeyboardRemove())
        user_data['slot'] = slot
        return 2

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_get_amount(self, bot, update, user_data):
        amount = str(update.message.text)
        if amount == 'Beenden':
            return self.maxamount_cancel(bot, update)
        if 'slot' not in user_data:
            update.message.reply_text('Kein Slot gesetzt.\nFür welchen Slot soll die Maximalmenge aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=False))
            return 1
        slot = user_data['slot']

        try:
            amount = int(amount)
        except ValueError:
            update.message.reply_text('Ungültiger Wert.\nAuf welche Maximalmenge soll der Slot '+str(slot)+' aktualisiert werden?', reply_markup = ReplyKeyboardRemove())
            return 2
        
        if not amount > 0:
            update.message.reply_text('Ungültiger Wert.\nAuf welche Maximalmenge soll der Slot '+str(slot)+' aktualisiert werden?', reply_markup = ReplyKeyboardRemove())
            return 2
        user_data.pop('slot')
        self.update_maxfillstatus_callback(slot, amount)
        update.message.reply_text('Slot '+str(slot)+' erfolgreich auf Maximalmenge '+str(amount)+' geändert.\nFür welchen Slot soll die Maximalmenge aktualisiert werden?', reply_markup = self.slot_keyboard(with_complete=False))
        return 1

    # maxamount_cancel
    # INFO:     Cancels the process of setting the maximum amount for a slot.
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def maxamount_cancel(self, bot, update):
        update.message.reply_text('Vorgang beendet.')
        self.admin_panel(bot, update)
        return ConversationHandler.END

    # ban_entry
    # INFO:     Introduction to the user banning conversation.
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def ban_entry(self, bot, update):
        update.message.reply_text('Welche Telegram-ID soll gesperrt werden?\nAbbrechen mit \'Abbruch\'.', reply_markup = ReplyKeyboardRemove())
        return 1

    # ban_get_id
    # INFO:     Queries the admin for the Telegram ID to be banned. Will continue to either confirmation if id is valid or re-ask for id if it is invalid.
    # ARGS:     user_data (array) -> 'id' (str) Telegram ID of the user to be banned.
    # RETURNS:  /
    @admin_only
    def ban_get_id(self, bot, update, user_data):
        id_to_ban = str(update.message.text)
        if id_to_ban == 'Abbruch':
            return self.ban_cancel(bot, update)

        if re.compile("[^0-9]").match(id_to_ban) is not None:
            update.message.reply_text('Das ist eine ungültige ID.\nWelche Telegram-ID soll gesperrt werden?\nAbbrechen mit \'Abbruch\'.', reply_markup = ReplyKeyboardRemove())
            return 1
        
        if id_to_ban in self.blacklist_user_id:
            update.message.reply_text('ID '+str(id_to_ban)+' ist bereits gesperrt.')
            return self.ban_cancel(bot, update)
        update.message.reply_text('Bitte bestätigen, dass die Telegram-ID '+str(id_to_ban)+' gesperrt werden soll:', reply_markup = ReplyKeyboardMarkup([['Ja'], ['Abbruch']]))
        user_data['id'] = id_to_ban
        return 2

    # ban_get_confirmation
    # INFO:     Confirms the process of banning the specified user in user_data with the admin. Ends the conversation.
    # ARGS:     user_data (array) -> 'id' (str) Telegram ID of the user to be banned.
    # RETURNS:  /
    @admin_only
    def ban_get_confirmation(self, bot, update, user_data):
        answer = str(update.message.text)
        if answer == 'Abbruch':
            return self.ban_cancel(bot, update)
        if 'id' not in user_data:
            update.message.reply_text('Keine ID gesetzt.\nWelche Telegram-ID soll gesperrt werden?\nAbbrechen mit \'Abbruch\'.', reply_markup = ReplyKeyboardRemove())
            return 1
        id_to_ban = user_data['id']
        user_data.pop('id')
        id_of_admin = str(update.effective_user.id)
        self.ban_user_in_db(id_to_ban, id_of_admin)
        self.blacklist_user_id.append(id_to_ban)
        update.message.reply_text('Telegram ID '+str(id_to_ban)+' erfolgreich gesperrt.')
        self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-ID '+str(id_to_ban)+' wurde von '+str(id_of_admin)+' gesperrt.', disable_notification=True)
        self.admin_panel(bot, update)
        return ConversationHandler.END

    # ban_cancel
    # INFO:     Stops the conversation about banning a user.
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def ban_cancel(self, bot, update):
        update.message.reply_text('Vorgang beendet.')
        self.admin_panel(bot, update)
        return ConversationHandler.END

    # reload_databases
    # INFO:     Will re-read all database contents and configuration files from file.
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def reload_databases(self, bot, update):
        self.read_cfg()
        self.initialise_db()
        update.message.reply_text('Datenbanken werden neu gelesen.')
        self.admin_panel(bot, update)

    # restart_service
    # INFO:     Restarts the entire program by shutting down the telegram thread, which in turn causes the main thread to end. The system service manager will then restart the service after its timeout.
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def restart_service(self, bot, update):
        update.message.reply_text('Automat wird neu gestartet. Bitte etwas Geduld.')
        self.admin_panel(bot, update)
        self.logger.warning('Restart was initiated. Will shut down process now.')
        self.shutdown = True
        self.is_running = False

    # answer_report
    # INFO:     
    # ARGS:     /
    # RETURNS:  /
    @admin_only
    def answer_report(self, bot, update, args):
        user_id = args[0]
        message = " ".join(args[1:])
        if re.compile("[^0-9]").match(user_id) is not None:
            update.message.reply_text('Das ist eine ungültige ID.', reply_markup = ReplyKeyboardRemove())
            return
        self.tbot_up.bot.send_message(chat_id=user_id, text='Antwort der Admins auf deine Meldung:\n\n'+message)

    # update_fillstatus_callback
    # INFO:     Checks if slot to be changed is valid, then either decrements the amount in that slot by 1 if amount is None, otherwise update slot content to amount both locally in array as well as in database. Handles admin group notifications by comparing the new slot amount to the notification levels specified in the class. 
    # ARGS:     slot (int) -> chosen slot to update, amount (int) -> amount to set slot to, will decrease amount by 1 if no amount specified
    # RETURNS:  /
    def update_fillstatus_callback(self, slot, amount = None):
        if slot not in self.automat_content:
            self.logger.error('Received content update for slot '+str(slot)+' which is unknown. Dismissing.')
            return
        old_amount = self.automat_content[slot]['amount']
        if amount is None:
            if old_amount <= 0:
                self.logger.error('Received decrement content update for slot '+str(slot)+' which was assumed to be empty.')
                new_amount = 0
            else:
                self.logger.debug('Received decrement content update for slot '+str(slot)+', which had '+str(old_amount)+' in it.')
                new_amount = old_amount - 1
        else:
            self.logger.debug('Received set content update for slot '+str(slot)+' with specified new amount '+str(amount))
            new_amount = amount
        self.automat_content[slot]['amount'] = new_amount
        self.set_amount_in_db(slot, amount = new_amount)

        if new_amount is 0:
            self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Slot '+str(slot)+' ist leer!', disable_notification=False)
        elif old_amount > new_amount:
            relative_fill_level = new_amount/self.automat_content[slot]['max_amount']
            current_notification_level = self.automat_content[slot]['notification_level']
            if relative_fill_level <= self.notification_content_levels[current_notification_level]:
                self.automat_content[slot]['notification_level'] = current_notification_level + 1
                self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Slot '+str(slot)+' ist nur noch '+str(int(relative_fill_level*100))+'% gefüllt, mit '+str(new_amount)+' von '+str(self.automat_content[slot]['max_amount'])+'.', disable_notification=True)
        elif old_amount < new_amount:
            self.automat_content[slot]['notification_level'] = 0

    # uppdate_maxfillstatus_callback
    # INFO:     Checks if slot to be changed is valid, then adjusts maximum amount to maxamount in local array and in database.
    # ARGS:     slot (int) -> chosen slot to update, maxamount (int) -> maximum amount to set slot to
    # RETURNS:  /
    def update_maxfillstatus_callback(self, slot, maxamount):
        if slot not in self.automat_content:
            self.logger.error('Received max-content update for slot '+str(slot)+' which is unknown. Dismissing.')
            return
        if maxamount < 0:
            self.logger.error('Received max-content update for slot '+str(slot)+' which is negative. Dismissing.')
            return
        self.logger.debug('Received set max-content update for slot '+str(slot)+' with specified new max-amount '+str(maxamount))
        self.automat_content[slot]['max_amount'] = maxamount
        self.set_amount_in_db(slot, max_amount = maxamount)


# main executable
if __name__ == "__main__":
    print('Hi')
