import os
import time
import sys
import requests
import yaml
from datetime import datetime
from prometheus_client import Enum, start_http_server, Gauge

VERSION="1.0.3"

config_file = "config.yaml"

if len(sys.argv) > 1:
  config_file = sys.argv[1]

with open(config_file, "r") as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)
        os.exit(1)

start_http_server(config.get("port", "9091"))

sleep_time = int(config.get("sleep", 30))
debug = config.get('debug', False) in [True, "true", "TRUE", "True", "1", 1]
env = config.get('env', "prod").lower()

def check_wallets():
  for chain_id, wallets in config.get('wallets', {}).items():
    for wallet, wallet_name in wallets.items():
      try:
        balance_req = requests.get((config.get("lcd")+"/cosmos/bank/v1beta1/balances/{}").format(chain_id+"." if chain_id != "default" else "", url_env, wallet))
        balance = balance_req.json().get('balances',[])
        for item in balance:
          g_wallet_balance.labels(chain_id, wallet, wallet_name, item.get('denom')).set(item.get('amount'))
        time.sleep(200/1000) ## 200ms
      except requests.exceptions.RequestException as e:
        print("error: {}".format(e))

def dbg_print(*args):
  if debug:
    print(*args)

def get_price(chain_id, denom, cgid):
  url = "https://coingecko.p.rapidapi.com/coins/{}".format(cgid)
  querystring = {"localization":"true","tickers":"true","market_data":"true","community_data":"true","developer_data":"true","sparkline":"false"}
  headers = {"X-RapidAPI-Key": config.get("coingecko_api_key"),"X-RapidAPI-Host": "coingecko.p.rapidapi.com"}
  try:
    response = requests.request("GET", url, headers=headers, params=querystring)
    value = float(response.json().get("market_data", {}).get("current_price", {}).get("usd", 0.00))
    if value == 0.00:
      print("unable to get price for {}".format(cgid))
      return
    g_asset_price.labels(chain_id, denom).set(value)
  except requests.exceptions.RequestException as e:
        print("error: {}".format(e))

## determine url prefix for env
if env in ['prod', '']:
  url_env = ''
else:
  url_env = env + '.'

g_receipt_count = Gauge('qsd_receipt_count', "Number of unique deposit receipts", ['chain_id'])
g_depositor_count = Gauge('qsd_depositor_count', "Number of unique depositor addresses", ['chain_id'])
g_deposit_amount = Gauge('qsd_deposit_amount', "Total value deposited", ['chain_id'])
g_delegated_amount = Gauge('qsd_delegated_amount', "Total amount delegated according to QS", ['chain_id'])
g_supply_amount = Gauge('qsd_supply_amount', "Total qAsset supply", ['chain_id'])
g_wallet_balance = Gauge('qsd_wallet_balance', "Wallet balance", ['chain_id', 'wallet', 'wallet_name', 'denom'])
g_ibc_acknowledgement_queue = Gauge('qsd_ibc_acks', "IBC Acknowledgement Queue", ['chain_id', 'channel', 'port'])
g_ibc_commitment_queue = Gauge('qsd_ibc_commitments', "IBC Commitment Queue", ['chain_id', 'channel', 'port'])
g_icq_oldest_emission_distance = Gauge('qsd_icq_oldest_emission_distance', "Distance between oldest emission height and current block", ['chain_id'])
g_icq_historic_queue = Gauge('qsd_icq_historic_queue', "ICQ Queue Length", ['chain_id'])
g_asset_price = Gauge('qsd_base_asset_price', "Base asset price for zone", ["chain_id", "denom"])
g_redemption_rate = Gauge('qsd_redemption_rate', "Redemption rate for zone", ["chain_id"])

zone_req = requests.get((config.get('lcd')+"/quicksilver/interchainstaking/v1/zones").format("", url_env))
zones = zone_req.json().get('zones')

while True:
  try:
    supply_req = requests.get((config.get("lcd")+"/cosmos/bank/v1beta1/supply").format("", url_env))
    supply = supply_req.json().get("supply")
  except requests.exceptions.RequestException as e:
        print("error: {}".format(e))

  for chain_id, chain_data in config.get('chains').items():
    zone = [x for x in zones if x.get('chain_id') == chain_id][0]
    cgid = chain_data.get('coingecko_id', False)
    if cgid:
      get_price(chain_id, zone.get('base_denom'), cgid)
    dbg_print("=================== {} ({})  ===================".format(datetime.now(), chain_id))
    g_redemption_rate.labels(chain_id).set(float(zone.get('redemption_rate')))
    this_token = [int(x.get("amount", 0)) for x in supply if x.get("denom") == zone.get("local_denom")][0]
    g_supply_amount.labels(chain_id).set(this_token)
    try:
      delegation_req = requests.get((config.get("lcd")+"/quicksilver/interchainstaking/v1/zones/{}/delegations").format("", url_env, chain_id))
      delegated_tvl = int(delegation_req.json().get('tvl'))
      dbg_print("Total delegated:", delegated_tvl)
      g_delegated_amount.labels(chain_id).set(delegated_tvl)
    except requests.exceptions.RequestException as e:
      print("error: {}".format(e))
    depositors = {}
    try:
      receipt_req = requests.get((config.get("lcd")+"/quicksilver/interchainstaking/v1/zones/{}/receipts").format("", url_env, chain_id))
      receipts = receipt_req.json().get('receipts')

      for r in receipts:
        address = r.get('sender')
        previous = depositors.get(address, 0)
        amount = int(r.get('amount')[0].get("amount"))
        depositors.update({address: (amount+previous)})
      deposited_amount = sum(depositors.values())
      dbg_print("Total deposited:", deposited_amount, zone.get("base_denom"))
      g_deposit_amount.labels(chain_id).set(deposited_amount)
      dbg_print("Total supply:", this_token, zone.get("local_denom"))
      dbg_print("Number of receipts:", len(receipts))
      g_receipt_count.labels(chain_id).set(len(receipts))
      dbg_print("Number of depositors:", len(depositors))
      g_depositor_count.labels(chain_id).set(len(depositors))
      for addr, amount in depositors.items():
        dbg_print(" >> {}: {}".format(addr, amount/1e6))
    except requests.exceptions.RequestException as e:
      print("error: {}".format(e))

    ## current block height
    try:
      block = requests.get((config.get("rpc")+"/status").format("", url_env))
      current_height = int(block.json().get('result').get('sync_info').get('latest_block_height'))
    except requests.exceptions.RequestException as e:
      print("error: {}".format(e))

    ## icq queue
    try:
      icq_requests = requests.get((config.get("lcd")+"/quicksilver/interchainquery/v1/queries/{}").format("", url_env, chain_id))
      resp = icq_requests.json()
      g_icq_historic_queue.labels(chain_id).set(resp.get('pagination').get('total'))
      DEFAULT_LOWEST = 9999999999999999
      lowest = DEFAULT_LOWEST
      for x in resp.get('queries'):
        if int(x.get('last_emission')) < lowest:
          lowest = int(x.get('last_emission'))
        if lowest != DEFAULT_LOWEST:
          g_icq_oldest_emission_distance.labels(chain_id).set(current_height-lowest)
    except requests.exceptions.RequestException as e:
      print("error: {}".format(e))

    ## ibc queue
    for port, channel in chain_data.get("channels").items():
      try:
        ibc_packet_commitments_req = requests.get((config.get("lcd")+"/ibc/core/channel/v1/channels/{}/ports/icacontroller-{}.{}/packet_commitments").format("", url_env, channel, chain_id, port))
        ibc_packet_commitments = int(ibc_packet_commitments_req.json().get('pagination').get('total'))
        g_ibc_commitment_queue.labels(chain_id, channel, port).set(ibc_packet_commitments)
        ibc_packet_acks_req = requests.get((config.get("lcd")+"/ibc/core/channel/v1/channels/{}/ports/icacontroller-{}.{}/packet_commitments").format("", url_env, channel, chain_id, port))
        ibc_packet_acks = int(ibc_packet_acks_req.json().get('pagination').get('total'))
        g_ibc_acknowledgement_queue.labels(chain_id, channel, port).set(ibc_packet_acks)
      except requests.exceptions.RequestException as e:
        print("error: {}".format(e))

  check_wallets()
  time.sleep(sleep_time)
