import subprocess, json, os, time

result = subprocess.run(
    ["ssh", "-i", os.path.expanduser("~/.ssh/fortress_vps"),
     "-o", "StrictHostKeyChecking=no",
     "ubuntu@76.13.138.194", "cat /home/ubuntu/.fortress_api_token"],
    capture_output=True, text=True
)
TOKEN = result.stdout.strip()

env = os.environ.copy()
env["FORTRESS_API_URL"] = "http://76.13.138.194:8080"
env["FORTRESS_API_TOKEN"] = TOKEN


def call_mcp_tool(tool_name, arguments=None):
    if arguments is None:
        arguments = {}
    proc = subprocess.Popen(
        ["python3.11", "/home/ubuntu/fortress_mcp/fortress_mcp.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env
    )
    messages = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "manus", "version": "1.0"}}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments}}) + "\n",
    ]
    for msg in messages:
        proc.stdin.write(msg.encode())
    proc.stdin.flush()
    time.sleep(3)
    proc.terminate()
    out = proc.stdout.read().decode()
    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            if d.get("id") == 2:
                content = d.get("result", {}).get("content", [])
                if content:
                    text = content[0].get("text", "")
                    try:
                        return json.loads(text)
                    except:
                        return text
        except:
            pass
    return None


data = {}

# Active positions with known tickers and strategies
active_positions = [
    ("MSFT", "pmcc"),
    ("AVGO", "pmcc"),
    ("VST", "pmcc"),
    ("NFLX", "pmcc"),
    ("UNH", "pcs"),
]

# Stop-loss evaluation per position
for ticker, strategy in active_positions:
    print(f"evaluate_stop_loss {ticker}...")
    data[f"stop_loss_{ticker}"] = call_mcp_tool("evaluate_stop_loss", {"ticker": ticker})

# Roll evaluation per position
for ticker, strategy in active_positions:
    print(f"evaluate_roll {ticker}...")
    data[f"roll_{ticker}"] = call_mcp_tool("evaluate_roll", {"ticker": ticker})

# Pre-trade check for new entry candidates
new_candidates = [
    ("NVDA", "pmcc"),
    ("AMD", "pmcc"),
    ("GOOGL", "pmcc"),
    ("META", "pmcc"),
    ("AAPL", "pmcc"),
]
for ticker, strategy in new_candidates:
    print(f"pretrade_check {ticker}...")
    data[f"pretrade_{ticker}"] = call_mcp_tool("pretrade_check", {"ticker": ticker, "strategy": strategy})

with open("/home/ubuntu/position_analysis2.json", "w") as f:
    json.dump(data, f, indent=2)

print("Done.")
