import json
import time
import uuid
from datetime import datetime, timedelta

import slack
from telegram import Bot

from utils.myconfig import ConfigLoader

config = ConfigLoader.load_config()


def get_timestamp():
    return int(time.time() * 1000)


def get_now_datetime():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    return formatted_time


def get_report_days():
    statistical_days = config["common"]["statistical_days"]
    now = datetime.now()
    end_time = now
    start_time = now - timedelta(days=statistical_days)
    return start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def convert_list_to_json_array(symbols):
    if symbols is None:
        return symbols
    res = json.dumps(symbols)
    return res.replace(" ", "")


def get_uuid():
    return str(uuid.uuid4())


def clean_none_value(d):
    out = {}
    for k in d.keys():
        if d[k] is not None:
            out[k] = d[k]
    return out


def send_alert_message(ok_count, fail_count):
    alert_message = f'WOOFi Pro {config["common"]["network"]} - update-user-rate-base-volume, ok_count: {ok_count}, fail_count: {fail_count}'
    Bot(config["common"]["telegram_bot_token"]).send_message(
        config["common"]["telegram_chat_id"], alert_message, reply_to_message_id=config["common"]["telegram_message_id"]
    )
    slack.WebClient(config["common"]["slack_bot_token"]).chat_postMessage(
        channel=config["common"]["slack_channel"], text=alert_message
    )


class Error(Exception):
    pass


class ClientError(Error):
    def __init__(self, status_code, error_code, error_message, header, error_data=None):
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message
        self.header = header
        self.error_data = error_data


class ServerError(Error):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
