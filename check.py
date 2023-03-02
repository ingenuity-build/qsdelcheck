import requests
import os
import time
from datetime import datetime
from prometheus_client import Enum, start_http_server, Gauge


start_http_server(9092)

sleep_time = int(os.environ.get("QSDELCHECK_SLEEP", 30))
chain_id = os.environ.get("QSDELCHECK_CHAIN")
debug = os.environ.get("QSDELCHECK_DEBUG", False) in [True, "true", "TRUE", "True", "1", 1]
env = os.environ.get("QSDELCHECK_ENV", "prod").lower()
wallets = os.environ.get("QSDELCHECK_WALLETS", "").split(",")

## determine url prefix for env
if env in ['prod', '']:
  url_env = ''
else:
  url_env = env + '.'

def dbg_print(*args):
  if debug:
    print(*args)

g_receipt_count = Gauge('receipt_count', "Number of unique deposit receipts")
g_depositor_count = Gauge('depositor_count', "Number of unique depositor addresses")
g_deposit_amount = Gauge('deposit_amount', "Total value deposited")
g_delegated_amount = Gauge('delegated_amount', "Total amount delegated according to QS")
g_true_delegated_amount = Gauge('true_delegated_amount', "Total amount delegated according to host")
g_supply_amount = Gauge('supply_amount', "Total qAsset supply")
g_wallet_balance = Gauge('qsd_wallet_balance', "Wallet balance", ['wallet', 'denom'])
g_ibc_acknowledgement_queue = Gauge('qsd_ibc_acks', "IBC Acknowledgement Queue")
g_ibc_commitment_queue = Gauge('qsd_ibc_commitments', "IBC Commitment Queue")
g_icq_oldest_emission_distance = Gauge('qsd_icq_oldest_emission_distance', "Distance between oldest emission height and current block")
g_icq_historic_queue = Gauge('qsd_icq_historic_queue', "ICQ Queue Length")

zone_req = requests.get("https://lcd.{}quicksilver.zone/quicksilver/interchainstaking/v1/zones".format(url_env))
zones = zone_req.json().get('zones')
zone = [x for x in zones if x.get('chain_id') == chain_id][0]
#delegation_address = zone.get('delegation_address').get('address')

while True:
  dbg_print("=================== {} ===================".format(datetime.now()))
  supply_req = requests.get("https://lcd.{}quicksilver.zone/cosmos/bank/v1beta1/supply".format(url_env))
  supply = supply_req.json().get("supply")
  this_token = [int(x.get("amount", 0)) for x in supply if x.get("denom") == zone.get("local_denom")][0]
  g_supply_amount.set(this_token)
  delegation_req = requests.get("https://lcd.{}quicksilver.zone/quicksilver/interchainstaking/v1/zones/{}/delegations".format(url_env, chain_id))
  delegated_tvl = int(delegation_req.json().get('tvl'))

  receipt_req = requests.get("https://lcd.{}quicksilver.zone/quicksilver/interchainstaking/v1/zones/{}/receipts".format(url_env, chain_id))
  receipts = receipt_req.json().get('receipts')

  dbg_print("Total delegated:", delegated_tvl)
  g_delegated_amount.set(delegated_tvl)
  depositors = {}
  for r in receipts:
    address = r.get('sender')
    previous = depositors.get(address, 0)
    amount = int(r.get('amount')[0].get("amount"))
    depositors.update({address: (amount+previous)})
  deposited_amount = sum(depositors.values())
  dbg_print("Total deposited:", deposited_amount, zone.get("base_denom"))
  g_deposit_amount.set(deposited_amount)
  dbg_print("Total supply:", this_token, zone.get("local_denom"))
  dbg_print("Number of receipts:", len(receipts))
  g_receipt_count.set(len(receipts))
  dbg_print("Number of depositors:", len(depositors))
  g_depositor_count.set(len(depositors))
  for addr, amount in depositors.items():
    dbg_print(" >> {}: {}".format(addr, amount/1e6))

  ## true delegated amount
  #true_delegated_req = requests.get("https://lcd.{}.{}quicksilver.zone/cosmos/staking/v1beta1/delegations/{}".format(chain_id, url_env, zone.get('delegation_address').get('address'))
  
  ## wallet balances
  if len(wallets[0]) > 0:
    for wallet in wallets:
      balance_req = requests.get("https://lcd.{}.{}quicksilver.zone/cosmos/bank/v1beta1/balances/{}".format(chain_id, url_env, wallet))
      balance = balance_req.json().get('balances',[])
      for item in balance:
        g_wallet_balance.labels(wallet, item.get('denom')).set(item.get('amount'))          

  ## current block height
  block = requests.get("https://rpc.{}quicksilver.zone/status".format(url_env))
  current_height = int(block.json().get('result').get('sync_info').get('latest_block_height'))

  ## icq queue
  icq_requests = requests.get("https://lcd.{}quicksilver.zone/quicksilver/interchainquery/v1/queries/{}".format(url_env, chain_id))
  resp = icq_requests.json()
  g_icq_historic_queue.set(resp.get('pagination').get('total'))
  DEFAULT_LOWEST = 9999999999999999
  lowest = DEFAULT_LOWEST
  for x in resp.get('queries'):
    if int(x.get('last_emission')) < lowest:
      lowest = int(x.get('last_emission'))
  if lowest != DEFAULT_LOWEST:
    g_icq_oldest_emission_distance.set(current_height-lowest)
  time.sleep(sleep_time)


