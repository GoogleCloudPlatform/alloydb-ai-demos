from __future__ import annotations
from src.utils.sql import fetchall, execute
from src.agents.coordinator import recommend_replenishment

def pick_one_sku_store():
    rows=fetchall("SELECT t.sku, t.store_id, COUNT(*) AS c FROM retail.transactions t WHERE t.sku IS NOT NULL AND t.store_id IS NOT NULL GROUP BY 1,2 ORDER BY c DESC LIMIT 1")
    if not rows: raise RuntimeError("No transactions loaded")
    return rows[0]['store_id'], rows[0]['sku']

def ensure_baseline(store_id:int, sku:str):
    execute("INSERT INTO retail.stock_levels (store_id, sku, on_hand, in_transit, safety_stock, reorder_point) VALUES (%s,%s,20,0,10,15) ON CONFLICT (store_id, sku) DO NOTHING", (store_id, sku))
    execute("INSERT INTO retail.suppliers (name,lead_time_days,moq,email,terms) VALUES ('Supplier A',5,50,'a@supplier.example','NET30') ON CONFLICT DO NOTHING;")
    execute("INSERT INTO retail.product_suppliers (sku, supplier_id, preferred, cost, lead_time_days, moq) SELECT %s, s.supplier_id, TRUE, 4.20, 5, 50 FROM retail.suppliers s WHERE s.name='Supplier A' ON CONFLICT (sku, supplier_id) DO NOTHING", (sku,))

if __name__=='__main__':
    store_id, sku = pick_one_sku_store(); ensure_baseline(store_id, sku)
    result=recommend_replenishment(store_id, sku, horizon_days=14); print('RESULT:', result)
