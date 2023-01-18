import requests
import os
import time
from datetime import datetime
from prometheus_client import Enum, start_http_server, Gauge

start_http_server(9091)

chain_id = os.environ.get("QSDELCHECK_CHAIN", "stargaze-1")
debug = os.environ.get("QSDELCHECK_DEBUG", False) in [True, "true", "TRUE", "True", "1", 1]
env = os.environ.get("QSDELCHECK_ENV", "prod").lower()

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
#g_true_delegated_amount = Gauge('true_delegated_amount', "Total amount delegated according to host")
g_supply_amount = Gauge('supply_amount', "Total qAsset supply")

internal = [
"stars1f6g9guyeyzgzjc9l8wg4xl5x0rvxddewdqjv7v", ## aj
"stars16x03wcp37kx5e8ehckjxvwcgk9j0cqnh8qlue8", ## joe
"stars1954q9apawr6kg8ez4ukx8jyuaxakz7ye22ttyk", ## prakriti
]

zone_req = requests.get("https://lcd.{}quicksilver.zone/quicksilver/interchainstaking/v1/zones".format(url_env))
zones = zone_req.json().get('zones')
zone = [x for x in zones if x.get('chain_id') == chain_id][0]
#delegation_address = zone.get('delegation_address').get('address')

while True:
  dbg_print("=================== {} ===================".format(datetime.now()))
  supply_req = requests.get("https://lcd.{}quicksilver.zone/cosmos/bank/v1beta1/supply".format(url_env))
  supply = supply_req.json().get("supply")
  this_token = [int(x.get("amount")) for x in supply if x.get("denom") == zone.get("local_denom")][0]
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
    dbg_print(" >> {}: {} {}".format(addr, amount/1e6, "*" if addr in internal else ""))
  time.sleep(60)


