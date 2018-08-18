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
    automat_content = {'slot': {'amount': 0, 'max_amount': 0}}
    max_content_per_slot = 50


    # name
    # INFO:
    # ARGS:
    # RETURNS:
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


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def run(self):
        self.is_running = True

        self.tbot_up = Updater(self.telegram_api_key)
        self.tbot_dp = self.tbot_up.dispatcher
        self.tbot_jq = self.tbot_up.job_queue


        # general conversation handlers
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

        # admin only conversation handlers
        amount_handler = ConversationHandler(
            entry_points = [RegexHandler('(Füllstand ändern)', self.amount_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.amount_get_slot, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.amount_get_amount, pass_user_data=True)],
            },
            fallbacks = [CommandHandler('cancel', self.amount_cancel)]
        )
        self.tbot_dp.add_handler(amount_handler)

        maxamount_handler = ConversationHandler(
            entry_points = [RegexHandler('(Maximalmengen ändern)', self.maxamount_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.maxamount_get_slot, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.maxamount_get_amount, pass_user_data=True)],
            },
            fallbacks = [CommandHandler('cancel', self.maxamount_cancel)]
        )
        self.tbot_dp.add_handler(maxamount_handler)

        ban_handler = ConversationHandler(
            entry_points = [RegexHandler('(User bannen)', self.ban_entry)],
            states = {
                1: [MessageHandler(Filters.text, self.ban_get_id, pass_user_data=True)],
                2: [MessageHandler(Filters.text, self.ban_get_confirmation, pass_user_data=True)],
            },
            fallbacks = [CommandHandler('cancel', self.ban_cancel)]
        )
        self.tbot_dp.add_handler(ban_handler)


        # admin only commands
        self.tbot_dp.add_handler(RegexHandler("(Administratives)", self.admin_panel))
        self.tbot_dp.add_handler(RegexHandler("(Zurück zur Übersicht)", self.default_state))


        # fallback command
        self.tbot_dp.add_handler(RegexHandler(".*", self.help))

        # log all errors
        self.tbot_dp.add_error_handler(self.error)

        # start telegram bot
        self.tbot_up.start_polling()

        # signal startup is finished
        self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-Bot Thread wurde gestartet.', disable_notification=True)

        while self.is_running:
            time.sleep(1)
        
        # signal shutdown
        self.tbot_up.bot.send_message(chat_id=self.admin_group_id, text='Telegram-Bot Thread wurde gestoppt.', disable_notification=True)


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
    def read_cfg(self):
        config = configparser.SafeConfigParser()
        config.read(self.cfg_path)
        self.telegram_api_key = str(config['telegram']['api_key'])
        self.admin_group_id = int(config['telegram']['admin_group_id'])
        self.logger.info('config loaded')


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def register_user_in_db(self, id, rfid):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        db.execute("INSERT INTO users (ID, rfid) VALUES ('"+str(id)+"','"+str(rfid)+"')")
        db_connector.commit()

        db_connector.close()
        self.logger.info('ID '+str(id)+ ' with RFID '+str(rfid)+' successfully registered in database.')
        return True


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def set_amount_in_db(self, slot, amount = None, max_amount = None):
        db_connector = sqlite3.connect(self.db_path)
        db = db_connector.cursor()

        if amount is not None:
            db.execute("UPDATE automat SET amount = '"+str(amount)+"' WHERE slot = '"+str(slot)+"'")
            db_connector.commit()

        if max_amount is not None:
            db.execute("UPDATE automat SET max_amount = '"+str(max_amount)+"' WHERE slot = '"+str(slot)+"'")

        db_connector.close()
        self.logger.info('Amount in slot '+str(slot)+ ' updated to '+str(amount)+' successfully in database.')
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
        self.automat_content = {item[0]: {'amount': item[1], 'max_amount': item[2]} for item in db.fetchall()}

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


    def default_keyboard_for_admins(self):
        keyboard = [['Allgemeine Informationen anzeigen'],['Guthaben überprüfen', 'Füllstand überprüfen'], ['Problem melden', 'Hilfe'], ['Administratives']]
        return ReplyKeyboardMarkup(keyboard)


    def admin_keyboard(self):
        keyboard = [['Füllstand ändern'], ['Maximalmengen ändern'], ['User bannen'], ['Zurück zur Übersicht']]
        return ReplyKeyboardMarkup(keyboard)

    def slot_keyboard(self):
        keyboard = [['1', '2'], ['3', '4'], ['5', '6'], ['Beenden']]
        return ReplyKeyboardMarkup(keyboard)

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
        string = 'Momentaner Füllstand:\n\n'+''.join('Slot '+str(slot)+': '+str(slot_dict['amount'])+'/'+str(slot_dict['max_amount'])+'\n' for slot, slot_dict in self.automat_content.items())
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
        if str(update.effective_user.id) not in self.users_rfid:
            update.message.reply_text('Um dein Guthaben abzurufen muss deine Legi-Identifikationsnummer mit deinem Telegram-Account in Verbindung gebracht werden. Ich werde mir die Legi-Identifikationsnummer merken und künftig direkt mit deinem Guthaben antworten.\n\nBitte sende mir deine Legi-Identifikationsnummer als Nachricht oder breche den Vorgang mit /cancel ab:', reply_markup = ReplyKeyboardRemove())
            return 1
        rfid = self.users_rfid[str(update.effective_user.id)]
        if rfid in self.rfid_data and time.time() < self.rfid_data[rfid]['timestamp'] + self.rfid_data_maxage:
            remaining_credits = self.rfid_data[rfid]['credits']
        else:
            conn = VCS_ID()
            data = conn.auth(rfid)
            if data is False:
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
        # present rfid submission dialogue, add /cancel info
        # ensure sanitisation!
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
        self.register_user_in_db(os.path.join(DB, "tbot.db"), update.effective_user.id, raw_rfid)
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
        update.message.reply_text('Welcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard())
        return 1


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def amount_get_slot(self, bot, update, user_data):
        slot = str(update.message.text)
        if slot == 'Beenden':
            self.admin_panel(bot, update)
            return ConversationHandler.END

        try:
            slot = int(slot)
        except ValueError:
            update.message.reply_text('Das ist ein ungültiger Slot.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard())
            return 1
        
        if slot not in self.automat_content:
            update.message.reply_text('Das ist ein ungültiger Slot.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard())
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
            self.admin_panel(bot, update)
            return ConversationHandler.END
        if 'slot' not in user_data:
            update.message.reply_text('Kein Slot gesetzt.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard())
            return 1
        slot = user_data['slot']
        if amount == '*':
            amount = self.automat_content[slot]['max_amount']
            
        try:
            amount = int(amount)
        except ValueError:
            update.message.reply_text('Ungültiger Wert.\nAuf welche Menge soll der Slot '+str(slot)+' aktualisiert werden?\nSende \'*\' für die Maximalmenge, also '+str(self.automat_content[slot]['max_amount'])+'.', reply_markup = ReplyKeyboardRemove())
            return 2
        
        if not (amount > 0 and amount <= self.automat_content[slot]['max_amount']):
            update.message.reply_text('Ungültiger Wert.\nAuf welche Menge soll der Slot '+str(slot)+' aktualisiert werden?\nSende \'*\' für die Maximalmenge, also '+str(self.automat_content[slot]['max_amount'])+'.', reply_markup = ReplyKeyboardRemove())
            return 2
        user_data.pop('slot')
        self.update_fillstatus_callback(slot, amount)
        update.message.reply_text('Slot '+str(slot)+' erfolgreich auf '+str(amount)+' geändert.\nWelcher Slot soll aktualisiert werden?', reply_markup = self.slot_keyboard())
        return 1


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def amount_cancel(self, bot, update):
        self.admin_panel(bot, update)
        return ConversationHandler.END



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_entry(self, bot, update):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_get_slot(self, bot, update, user_data):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_get_amount(self, bot, update, user_data):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def maxamount_cancel(self, bot, update):
        self.admin_panel(bot, update)
        return ConversationHandler.END



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_entry(self, bot, update):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_get_id(self, bot, update, user_data):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_get_confirmation(self, bot, update, user_data):
        return ConversationHandler.END


    # name
    # INFO:
    # ARGS:
    # RETURNS:
    @admin_only
    def ban_cancel(self, bot, update):
        self.admin_panel(bot, update)
        return ConversationHandler.END



    # name
    # INFO:
    # ARGS:
    # RETURNS:
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


# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    print('Hi')
