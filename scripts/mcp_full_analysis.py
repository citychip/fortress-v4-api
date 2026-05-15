import subprocess, json, os, time

# Get token from VPS
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

tools_to_call = [
    ("briefing",    "get_briefing",       {}),
    ("positions",   "get_positions",      {}),
    ("capability",  "get_capability",     {}),
    ("candidates",  "get_candidates",     {}),
    ("calendar",    "get_calendar",       {}),
    ("stop_loss",   "get_stop_loss",      {}),
    ("hedge",       "get_hedge_status",   {}),
    ("roll_candidates", "get_roll_candidates", {}),
    ("manage_positions", "get_manage_positions", {}),
]

for key, tool, args in tools_to_call:
    print(f"Calling {tool}...", flush=True)
    result = call_mcp_tool(tool, args)
    data[key] = result

# Save all data to file for analysis
with open("/home/ubuntu/portfolio_data.json", "w") as f:
    json.dump(data, f, indent=2)

print("All data collected. Saved to /home/ubuntu/portfolio_data.json")
print(f"Keys: {list(data.keys())}")
