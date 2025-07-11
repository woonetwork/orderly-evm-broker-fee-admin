import datetime
import sys
import time
from decimal import Decimal

from controllers.api import (
    get_account,
    get_broker_users_fees,
    get_broker_default_rate,
    set_broker_default_rate,
    get_broker_users_volumes,
    get_user_fee_rates,
    set_broker_user_fee,
)
from controllers.evm import get_staking_bals
from utils.cache import JsonHandler
from utils.myconfig import ConfigLoader
from utils.mylogging import setup_logging
from utils.pd import BrokerFee, StakingBal
from utils.util import get_redis_client, send_message, is_evm_address, is_svm_address

config = ConfigLoader.load_config()
logger = setup_logging()

REDIS_HASH_GRACE_PERIOD_FORMAT = f'woofi_pro:hash_grace_period:tier%s:{config["common"]["orderly_network"].lower()}'
REDIS_HASH_ACCOUNT_ID2ADDRESS = f'woofi_pro:account_id2address:{config["common"]["orderly_network"].lower()}'

# NOTE: "all" / "evm" / "svm" / "none"
REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_NETWORK = f'woofi_pro:hosting_campaign_fixed_tier_network:{config["common"]["orderly_network"].lower()}'
# NOTE: "1" / "2" / "3" / "4" / "5" / "6"
REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER = f'woofi_pro:hosting_campaign_fixed_tier:{config["common"]["orderly_network"].lower()}'
REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_START_TS = f'woofi_pro:hosting_campaign_fixed_tier_start_ts:{config["common"]["orderly_network"].lower()}'
REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_END_TS = f'woofi_pro:hosting_campaign_fixed_tier_end_ts:{config["common"]["orderly_network"].lower()}'


def init_broker_fees():
    # 每次启动，将当前Broker所有用户费率配置情况更新到本地数据库
    _count = 1
    broker_fee = BrokerFee(_type="broker_user_fee")
    # address2fee_rate = {}
    while True:
        data = get_broker_users_fees(_count)
        if not data or not data.get("data"):
            alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - get_broker_users_fees failed, _count: {_count}'
            send_message(alert_message)
            break
        if not data["data"].get("rows"):
            break
        if data:
            for _data in data["data"]["rows"]:
                logger.info(_data)
                # address2fee_rate[_data["address"]] = {
                #     "futures_maker_fee_rate": _data["maker_fee_rate"],
                #     "futures_taker_fee_rate": _data["taker_fee_rate"],
                # }
                broker_fee.create_update_user_fee_data(_data, delete_flag=True)
        _count += 1
        time.sleep(1)

    # verify_broker_fees_data(address2fee_rate, init_broker_fees.__name__)


# def verify_broker_fees_data(address2fee_rate, caller_func):
#     broker_fee = BrokerFee(_type="broker_user_fee")
#     for _address, _fee_rate in address2fee_rate.items():
#         query_result = broker_fee.pd.query_data_by_address(_address)
#         if query_result.empty:
#             alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - caller_func: {caller_func}, address: {_address}, futures_maker_fee_rate: {_fee_rate["futures_maker_fee_rate"]}, futures_taker_fee_rate: {_fee_rate["futures_taker_fee_rate"]} not updated'
#             logger.info(alert_message)
#         else:
#             futures_maker_fee_rate = query_result["futures_maker_fee_rate"].iloc[0]
#             futures_taker_fee_rate = query_result["futures_taker_fee_rate"].iloc[0]
#             if _fee_rate["futures_maker_fee_rate"] != futures_maker_fee_rate:
#                 alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - caller_func: {caller_func}, address: {_address}, csv futures_maker_fee_rate: {futures_maker_fee_rate}, actual futures_maker_fee_rate: {_fee_rate["futures_maker_fee_rate"]}'
#                 logger.info(alert_message)
#             if _fee_rate["futures_taker_fee_rate"] != futures_taker_fee_rate:
#                 alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - caller_func: {caller_func}, address: {_address}, csv futures_taker_fee_rate: {futures_taker_fee_rate}, actual futures_taker_fee_rate: {_fee_rate["futures_taker_fee_rate"]}'
#                 logger.info(alert_message)


def init_staking_bals():
    staking_bals = get_staking_bals()
    if staking_bals:
        # address2bal = {}
        user_fee = BrokerFee(_type="broker_user_fee")
        address2account_ids = {}

        for _row in user_fee.pd.df.itertuples():
            if _row.address not in address2account_ids:
                address2account_ids[_row.address] = [_row.account_id]
            else:
                address2account_ids[_row.address].append(_row.account_id)

        staking_bal = StakingBal(_type="staking_user_bal")
        # verify_address2account_id = {}
        # address2account_id = JsonHandler("address2account_id")
        # broker_id = "woofi_pro"
        for _bal in staking_bals:
            account_ids = address2account_ids.get(_bal["address"], [])
            for account_id in account_ids:
                staking_bal.create_update_user_bal_data({
                    "account_id": account_id,
                    "bal": _bal["bal"],
                    "address": _bal["address"],
                }, delete_flag=True)

            # account_id = address2account_id.get_content(_bal["address"])
            # if account_id is None:
            #     retry = 3
            #     while retry > 0:
            #         data = get_account(_bal["address"], broker_id)
            #         time.sleep(0.1)
            #         if not data or (not data.get("data") and data.get("message", "") != "Account not found."):
            #             retry -= 1
            #             alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - get_account failed, address: {_bal["address"]}, retry: {retry}'
            #             logger.info(alert_message)
            #             continue
            #         else:
            #             break
            #     if data is None:
            #         alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - get_account failed, address: {_bal["address"]}, retry: {retry}'
            #         send_message(alert_message)
            #         continue
            #     if data.get("message", "") == "Account not found.":
            #         logger.info(f'address: {_bal["address"]} account not found')
            #         continue
            #     account_id = data["data"]["account_id"]
            #     address2account_id.update_content(_bal["address"], account_id)
            #     # verify_address2account_id[_bal["address"]] = account_id
            #     logger.info(f'address: {_bal["address"]}, get account_id: {account_id}')
            # address2bal[_bal["address"]] = _bal["bal"]
            # staking_bal.create_update_user_bal_data({
            #     "account_id": account_id,
            #     "bal": _bal["bal"],
            #     "address": _bal["address"],
            # }, delete_flag=True)

        # address2account_id.write_json()

        # verify_address2account_id_write(verify_address2account_id)

        # verify_staking_bals_data(address2bal)


# def verify_address2account_id_write(verify_address2account_id):
#     address2account_id = JsonHandler("address2account_id")
#     for _address, _account_id in verify_address2account_id.items():
#         if address2account_id.get_content(_address) != _account_id:
#             alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - address: {_address}, account_id: {_account_id} not updated'
#             logger.info(alert_message)


# def verify_staking_bals_data(address2bal):
#     staking_bal = StakingBal(_type="staking_user_bal")
#     for _address, _bal in address2bal.items():
#         query_result = staking_bal.pd.query_data_by_address(_address)
#         if query_result.empty:
#             alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - address: {_address}, bal: {_bal} not updated'
#             logger.info(alert_message)
#         else:
#             bal = query_result["bal"].iloc[0]
#             if _bal != bal:
#                 alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} Debug - address: {_address}, csv bal: {bal}, actual bal: {_bal}'
#                 logger.info(alert_message)


def fetch_broker_default_rate():
    get_broker_default_rate()


def update_broker_default_fee(maker_fee, taker_fee):
    url = "/v1/broker/fee_rate/default"
    try:
        _data = get_broker_default_rate()
        if _data:
            logger.info(
                f'Modifying Broker Default Fees:  Maker Fee {_data["data"]["maker_fee_rate"]}->{maker_fee},Taker Fee {_data["data"]["taker_fee_rate"]}->{taker_fee}'
            )
        set_broker_default_rate(maker_fee, taker_fee)
    except Exception as e:
        logger.error(f"Get Broker Default Fee URL Failed: {url} - {e}")


def update_user_special_rate(account_id, maker_fee, taker_fee):
    _whitelists = config["rate"]["special_rate_whitelists"]
    if "special_rate_whitelists" in config["rate"] and isinstance(
        config["rate"]["special_rate_whitelists"], list
    ):
        if account_id not in _whitelists:
            _whitelists.append(f"{account_id}")
    else:
        logger.info(f"Key '{config['rate']}' not found or is not a list.")
    _data = [
        {
            "account_id": account_id,
            "futures_maker_fee_rate": maker_fee,
            "futures_taker_fee_rate": taker_fee,
        }
    ]
    _ok_count, _fail_count = set_broker_user_fee(_data)
    if _ok_count == 1:
        ConfigLoader.save_config(config)
    logger.info(
        f"Update User's Special Rate: Account ID = {account_id}, Taker Fee = {taker_fee}, Maker Fee = {maker_fee}"
    )


def update_grace_period_user_rates(user_fee, tier_count):
    redis_client = get_redis_client()

    grace_period_tier_all_account_ids = []
    total_ok_count = 0
    total_fail_count = 0

    cur_timestamp = int(time.time())
    for tier_config in config["rate"]["fee_tier"]:
        tier = tier_config["tier"]
        tier_maker_fee = Decimal(tier_config["maker_fee"].replace("%", "")) / 100
        tier_taker_fee = Decimal(tier_config["taker_fee"].replace("%", "")) / 100

        redis_hash_grace_period = REDIS_HASH_GRACE_PERIOD_FORMAT % tier

        grace_period_tier_data = []
        for _account_id, _start_timestamp in redis_client.hgetall(redis_hash_grace_period).items():
            if int(_start_timestamp) <= cur_timestamp < int(_start_timestamp) + 30 * 86400:
                if _account_id not in grace_period_tier_all_account_ids:
                    grace_period_tier_all_account_ids.append(_account_id)

                _address = redis_client.hget(REDIS_HASH_ACCOUNT_ID2ADDRESS, _account_id)
                if _address is None:
                    alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - grace_period_config, _account_id: {_account_id}, _address: {_address}'
                    send_message(alert_message)
                    continue

                _ret = {
                    "account_id": _account_id,
                    "futures_maker_fee_rate": tier_maker_fee,
                    "futures_taker_fee_rate": tier_taker_fee,
                    "address": _address,
                }
                old_user_fee = user_fee.pd.query_data(_account_id)
                if not old_user_fee.empty:
                    _old_futures_maker_fee_rate = Decimal(old_user_fee.futures_maker_fee_rate.values[0])
                    _old_futures_taker_fee_rate = Decimal(old_user_fee.futures_taker_fee_rate.values[0])
                    if (
                        tier_maker_fee != _old_futures_maker_fee_rate
                        or tier_taker_fee != _old_futures_taker_fee_rate
                    ):
                        grace_period_tier_data.append(_ret)
                        user_fee.create_update_user_fee_data(_ret)
                else:
                    grace_period_tier_data.append(_ret)
                    user_fee.create_update_user_fee_data(_ret)

                tier_count[tier] += 1

        ok_count, fail_count = set_broker_user_fee(grace_period_tier_data)
        total_ok_count += ok_count
        total_fail_count += fail_count

        alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - update_grace_period_user_rates, tier: {tier}, ok_count: {ok_count}, fail_count: {fail_count}'
        send_message(alert_message)
        logger.info(alert_message)

    return grace_period_tier_all_account_ids, total_ok_count, total_fail_count


def update_user_rates():
    logger.info("Broker user rate update started")
    _count = 1
    user_fee = BrokerFee(_type="broker_user_fee")
    staking_bal = StakingBal(_type="staking_user_bal")
    account_id2data = {}
    address2account_ids = {}
    for _row in staking_bal.pd.df.itertuples():
        account_id2data[_row.account_id] = {
            "staking_bal": Decimal(_row.bal),
            "perp_volume": 0,
            "address": _row.address,
        }
        if _row.address not in address2account_ids:
            address2account_ids[_row.address] = [_row.account_id]
        else:
            address2account_ids[_row.address].append(_row.account_id)

    while True:
        _data = get_broker_users_volumes(_count)
        if not _data or not _data.get("data"):
            alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - get_broker_users_volumes failed, _count: {_count}'
            send_message(alert_message)
            break
        if not _data["data"].get("rows"):
            break
        if _data:
            for _row in _data["data"]["rows"]:
                account_ids = address2account_ids.get(_row["address"], [])
                for _account_id in account_ids:
                    if _account_id in account_id2data:
                        account_id2data[_account_id]["perp_volume"] = _row["perp_volume"]
                    else:
                        account_id2data[_account_id] = {
                            "staking_bal": 0,
                            "perp_volume": _row["perp_volume"],
                            "address": _row["address"],
                        }

                # _account_id = _row["account_id"]
                # if _account_id in account_id2data:
                #     account_id2data[_account_id]["perp_volume"] = _row["perp_volume"]
                # else:
                #     account_id2data[_account_id] = {
                #         "staking_bal": 0,
                #         "perp_volume": _row["perp_volume"],
                #         "address": _row["address"],
                #     }

        _count += 1
        time.sleep(2)

    account_id2address = {_row.account_id: _row.address for _row in user_fee.pd.df.itertuples()}
    for _account_id, _data in account_id2data.items():
        if _account_id not in account_id2address:
            account_id2address[_account_id] = _data["address"]

    special_rate_whitelists = config["rate"]["special_rate_whitelists"]
    tier_count = {_tier["tier"]: 0 for _tier in config["rate"]["fee_tier"]}

    grace_period_tier_all_account_ids, total_ok_count, total_fail_count = update_grace_period_user_rates(
        user_fee, tier_count
    )

    redis_client = get_redis_client()

    hosting_campaign_fixed_tier_network = redis_client.get(REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_NETWORK)
    hosting_campaign_fixed_tier = redis_client.get(REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER)

    hosting_campaign_fixed_tier_start_ts = redis_client.get(REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_START_TS)
    hosting_campaign_fixed_tier_end_ts = redis_client.get(REDIS_KEY_HOSTING_CAMPAIGN_FIXED_TIER_END_TS) or sys.maxsize

    tier_fee_rates = {
        _tier["tier"]: {
            "futures_maker_fee_rate": Decimal(_tier["maker_fee"].replace("%", "")) / 100,
            "futures_taker_fee_rate": Decimal(_tier["taker_fee"].replace("%", "")) / 100,
            "tier": _tier["tier"],
        }
        for _tier in config["rate"]["fee_tier"]
    }
    now = int(time.time())
    data = []
    for _account_id, _address in account_id2address.items():
        if _account_id in grace_period_tier_all_account_ids:
            continue

        perp_volume = account_id2data.get(_account_id, {}).get("perp_volume", 0)
        staking_bal = account_id2data.get(_account_id, {}).get("staking_bal", 0)

        _user_fee = get_user_fee_rates(perp_volume, staking_bal)
        if int(hosting_campaign_fixed_tier_start_ts) <= now < int(hosting_campaign_fixed_tier_end_ts):
            if (
                hosting_campaign_fixed_tier_network == "all"
                or (hosting_campaign_fixed_tier_network == "evm" and is_evm_address(_address))
                or (hosting_campaign_fixed_tier_network == "svm" and is_svm_address(_address))
            ) and int(_user_fee["tier"]) < int(hosting_campaign_fixed_tier):
                _user_fee = tier_fee_rates[hosting_campaign_fixed_tier]

        if not _user_fee:
            alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - get_user_fee_rates, _address: {_address}, perp_volume: {perp_volume}, staking_bal: {staking_bal}'
            send_message(alert_message)
            break
        if _account_id not in special_rate_whitelists:
            tier_count[_user_fee["tier"]] += 1
            _new_futures_maker_fee_rate = Decimal(_user_fee["futures_maker_fee_rate"])
            _new_futures_taker_fee_rate = Decimal(_user_fee["futures_taker_fee_rate"])
            old_user_fee = user_fee.pd.query_data(_account_id)
            if not old_user_fee.empty:
                _old_futures_maker_fee_rate = Decimal(old_user_fee.futures_maker_fee_rate.values[0])
                _old_futures_taker_fee_rate = Decimal(old_user_fee.futures_taker_fee_rate.values[0])
                try:
                    if (
                        _new_futures_maker_fee_rate
                        != _old_futures_maker_fee_rate
                        or _new_futures_taker_fee_rate
                        != _old_futures_taker_fee_rate
                    ):
                        maker_fee_rate = _new_futures_maker_fee_rate
                        taker_fee_rate = _new_futures_taker_fee_rate
                        logger.info(
                            f"{_account_id} - New Maker Fee Rate: {maker_fee_rate}, Smaller Taker Fee Rate: {taker_fee_rate}"
                        )
                        _ret = {
                            "account_id": _account_id,
                            "futures_maker_fee_rate": maker_fee_rate,
                            "futures_taker_fee_rate": taker_fee_rate,
                            "address": _address,
                        }
                        data.append(_ret)
                        user_fee.create_update_user_fee_data(_ret)
                except:
                    print(
                        f"New rates are not smaller than old rates: {_account_id}"
                    )
            else:
                _ret = {
                    "account_id": _account_id,
                    "futures_maker_fee_rate": _new_futures_maker_fee_rate,
                    "futures_taker_fee_rate": _new_futures_taker_fee_rate,
                    "address": _address,
                }
                data.append(_ret)
                user_fee.create_update_user_fee_data(_ret)

    # address2fee_rate = {
    #     _data["address"]: {
    #         "futures_maker_fee_rate": str(_data["futures_maker_fee_rate"]),
    #         "futures_taker_fee_rate": str(_data["futures_taker_fee_rate"]),
    #     }
    #     for _data in data
    # }
    # verify_broker_fees_data(address2fee_rate, update_user_rates.__name__)

    ok_count, fail_count = set_broker_user_fee(data)
    total_ok_count += ok_count
    total_fail_count += fail_count

    alert_message = f'WOOFi Pro {config["common"]["orderly_network"]} - update_user_rates, ok_count: {total_ok_count}, fail_count: {total_fail_count}'
    send_message(alert_message)

    report_message = f'WOOFi Pro {config["common"]["orderly_network"]} Tier Report {datetime.date.today().strftime("%Y-%m-%d")}\n\n'
    for tier, count in tier_count.items():
        report_message += f"tier {tier}: {count}\n"
    report_message.rstrip("\n")
    send_message(report_message)

    logger.info(report_message)
    logger.info("Broker user rate update completed")


def update_user_rate():
    logger.info(
        "========================Orderly EVM Broker Fee Admin Startup========================"
    )
    init_broker_fees()
    init_staking_bals()
    update_user_rates()
