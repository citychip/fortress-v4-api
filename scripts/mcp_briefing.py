import subprocess, json, os, time

TOKEN = open(os.path.expanduser("~/.ssh/fortress_token"), "r").read().strip() if os.path.exists(os.path.expanduser("~/.ssh/fortress_token")) else ""

# Get token from VPS
import subprocess as sp
result = sp.run(
    ["ssh", "-i", os.path.expanduser("~/.ssh/fortress_vps"),
     "-o", "StrictHostKeyChecking=no",
     "ubuntu@YOUR_VPS_IP", "cat /home/ubuntu/.fortress_api_token"],
    capture_output=True, text=True
)
TOKEN = result.stdout.strip()

env = os.environ.copy()
env["FORTRESS_API_URL"] = "http://YOUR_VPS_IP:8080"
env["FORTRESS_API_TOKEN"] = TOKEN

def call_mcp_tool(tool_name, arguments=None):
    """Call a single MCP tool and return the result."""
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
                result = d.get("result", {})
                content = result.get("content", [])
                if content:
                    text = content[0].get("text", "")
                    try:
                        return json.loads(text)
                    except:
                        return text
        except:
            pass
    return None


print("=" * 60)
print("FORTRESS DASHBOARD — LIVE MCP BRIEFING")
print("=" * 60)

# 1. Get briefing
print("\n[1/4] Fetching portfolio briefing...")
briefing = call_mcp_tool("get_briefing")
if briefing:
    print(json.dumps(briefing, indent=2))

# 2. Get capability
print("\n[2/4] Fetching Greeks backend capability...")
capability = call_mcp_tool("get_capability")
if capability:
    print(json.dumps(capability, indent=2))

# 3. Get alerts
print("\n[3/4] Fetching active alerts...")
alerts = call_mcp_tool("get_alerts")
if alerts:
    print(json.dumps(alerts, indent=2))

# 4. Get positions summary
print("\n[4/4] Fetching positions...")
positions = call_mcp_tool("get_positions")
if positions:
    print(json.dumps(positions, indent=2))

print("\n" + "=" * 60)
print("END OF MCP BRIEFING")
print("=" * 60)
