# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging
import time
import sqlite3
from functools import wraps
import configparser

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


#
# CONFIG
#






#
# GENERAL
#


def initialise_db(db_path):
    db_connector = sqlite3.connect(db_path)
    db = db_connector.cursor()

    db.execute('SELECT * FROM admins')
    global admin_user_id
    admin_user_id = [item[0] for item in db.fetchall()]

    db.execute('SELECT * FROM blacklist')
    global blacklist_user_id
    blacklist_user_id = [item[0] for item in db.fetchall()]

    db_connector.close()



def initialise_cfg(cfg_path):
    config = configparser.ConfigParser()
    config.read(cfg_path)

    global telegram_api_key
    telegram_api_key = str(config['telegram']['telegram_api_key'])

    global telegram_db_path
    telegram_db_path = str(config['telegram']['telegram_db_path'])

    global admin_group_id
    admin_group_id = int(config['telegram']['admin_group_id'])






def admin_only(func):
    @wraps(func)
    def wrapped(bot, update, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in admin_user_id:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(bot, update, *args, **kwargs)
    return wrapped


def get_name(update):
    name = ''
    if update.message.from_user.first_name:
        name += update.message.from_user.first_name
    if update.message.from_user.last_name:
        name += ' '
        name += update.message.from_user.last_name

    return name

def get_helptext(update):
    output = 'Hier ist was ich kann:\n'
    output += '\n/help Zeigt die Befehle'
    output += '\n/status Gibt den Füllstand des Automaten'
    output += '\n/puls Überprüft Bot auf Lebenszeichen'
    output += '\n/report <Meldung> Leitet eine Meldung an die Verantwortlichen weiter'

    user_id = update.effective_user.id
    if user_id in admin_user_id:
        output += '\n\nWeitere Befehle für Admins:'
        output += '\n/fillstatus <Zahl> Aktualisiert den Füllstand des Automaten auf <Zahl>'
        output += '\n/ban <ID> Blockt Meldungen von User mit dieser ID'

    return output

#
# COMMAND HANDLERS
#

# message upon bot initiation
def start(bot, update):
    name = get_name(update)
    help_text = get_helptext(update)
    update.message.reply_text('Hallo {}!\nIch bin ein Bot für den VCS-Bierautomaten. Bei Fragen & Feedback wende dich an bierko@vcs.ethz.ch.\n{}'.format(name, help_text))

#
def check_responsiveness(bot, update):
    update.message.reply_text('🤖')

#
def check_fill_status(bot, update):
    update.message.reply_text('🤖')

# handle a report
def report(bot, update, args):
    if not update.message.from_user.id in blacklist_user_id:
        update.message.reply_text('Deine Meldung wurde übermittelt!')
        name = get_name(update)

        bot.send_message(chat_id=admin_group_id, text='Meldung\n--------------\nvon {}\nID {}\num {}\n\n {}'.format(name, update.effective_user.id, update.message.date, ' '.join(args)), disable_notification=True)
    else:
        update.message.reply_text('Du darfst keine Meldungen mehr einreichen.\nHälst du das für einen Fehler, melde dich bei bierko@vcs.ethz.ch')

# help
def help(bot, update):
    update.message.reply_text(get_helptext(update))


# throw errors
def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"', update, error)

# change current fill status
@admin_only
def change_fillstatus(bot, update, args):
    update.message.reply_text('To be implemented!')

# ban a user id
@admin_only
def ban_userid(bot, update, args):
    update.message.reply_text('User ID {} wurde geblockt!'.format(args))





#
# MAIN LOOP
#
def main():

    initialise_cfg('config/config')
    initialise_db(telegram_db_path)

    tbot_up = Updater(telegram_api_key)
    tbot_dp = tbot_up.dispatcher
    tbot_jq = tbot_up.job_queue

    # general commands
    tbot_dp.add_handler(CommandHandler("start", start))
    tbot_dp.add_handler(CommandHandler("report", report, pass_args=True))
    tbot_dp.add_handler(CommandHandler("help", help))
    tbot_dp.add_handler(CommandHandler("status", check_fill_status))
    tbot_dp.add_handler(CommandHandler("puls", check_responsiveness))

    # admin only commands
    tbot_dp.add_handler(CommandHandler("ban", ban_userid, pass_args=True))
    tbot_dp.add_handler(CommandHandler("fillstatus", change_fillstatus, pass_args=True))

    # log all errors
    tbot_dp.add_error_handler(error)

    tbot_up.start_polling()




    tbot_up.idle()


if __name__ == '__main__':
    main()
