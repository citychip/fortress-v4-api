""" Workflow 03: Position Monitor v3.4 (Delta & Data Health Aware) """
import json
import pathlib
from datetime import datetime, timezone, timedelta

# ... (bestaande imports en config) ...

def check_position_health(pos, current_price, top_dp):
    # Nieuwe Delta-logica (simulatie op basis van prijs-strikes)
    delta = pos.get("current_delta", 0.20) # Dashboard haalt dit live op
    
    status = "  SAFE"
    if delta > 0.40:
        status = "  GAMMA RISK (DELTA > 0.40)" # Signaleren, niet blokkeren
    elif current_price < top_dp:
        status = "  THESIS BREAK"
        
    return status

def main():
    # Controleert op 'stale data' (>24u oud)
    mtime = pathlib.Path("active_positions.json").stat().st_mtime
    if (datetime.now().timestamp() - mtime) > 86400:
        print("  WARNING: Data is stale (>24h). Upload new IBKR screenshot.")
    # ... rest van de monitor logica ...