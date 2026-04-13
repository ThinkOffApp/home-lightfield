#!/usr/bin/env bash
#
# inject-dashboard.sh
#
# Injects the iPad Lovelace dashboard into Home Assistant's storage.
# This creates a new dashboard accessible at /lovelace-ipad/main
#
# Usage:
#   ./inject-dashboard.sh [HA_CONFIG_DIR]
#
# HA_CONFIG_DIR defaults to the Docker-mounted HA config directory.
# Adjust the default path below to match your setup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
YAML_SOURCE="${SCRIPT_DIR}/ipad-dashboard.yaml"
HA_CONFIG="${1:-/Users/petrus/home-lightfield/ha-config}"
STORAGE_DIR="${HA_CONFIG}/.storage"
STORAGE_FILE="${STORAGE_DIR}/lovelace.ipad"

# ---------- preflight checks ----------

if [ ! -f "$YAML_SOURCE" ]; then
  echo "ERROR: Dashboard YAML not found at ${YAML_SOURCE}" >&2
  exit 1
fi

if [ ! -d "$STORAGE_DIR" ]; then
  echo "ERROR: HA storage directory not found at ${STORAGE_DIR}" >&2
  echo "       Pass the HA config directory as an argument, e.g.:" >&2
  echo "       $0 /path/to/ha/config" >&2
  exit 1
fi

# ---------- backup existing ----------

if [ -f "$STORAGE_FILE" ]; then
  BACKUP="${STORAGE_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$STORAGE_FILE" "$BACKUP"
  echo "Backed up existing dashboard to ${BACKUP}"
fi

# ---------- generate storage JSON ----------

# We need python3 + PyYAML to convert YAML to the HA storage JSON format.
# If PyYAML is missing, fall back to a simpler approach.

python3 - "$YAML_SOURCE" "$STORAGE_FILE" << 'PYEOF'
import json
import sys
import time

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Install with: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

yaml_path = sys.argv[1]
output_path = sys.argv[2]

with open(yaml_path, "r") as f:
    dashboard = yaml.safe_load(f)

# HA .storage format for a custom dashboard (lovelace.<url_path>)
storage = {
    "version": 1,
    "minor_version": 1,
    "key": "lovelace.ipad",
    "data": {
        "config": dashboard
    }
}

with open(output_path, "w") as f:
    json.dump(storage, f, indent=2, ensure_ascii=False)

print(f"Written storage file to {output_path}")
PYEOF

# ---------- register the dashboard in lovelace_dashboards ----------

DASHBOARDS_FILE="${STORAGE_DIR}/lovelace_dashboards"

if [ -f "$DASHBOARDS_FILE" ]; then
  # Check if "ipad" dashboard is already registered
  if python3 -c "
import json, sys
with open('${DASHBOARDS_FILE}') as f:
    data = json.load(f)
items = data.get('data', {}).get('items', [])
for item in items:
    if item.get('url_path') == 'ipad':
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    echo "Dashboard 'ipad' already registered in lovelace_dashboards."
  else
    # Back up and add the dashboard entry
    cp "$DASHBOARDS_FILE" "${DASHBOARDS_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
    python3 - "$DASHBOARDS_FILE" << 'PYEOF2'
import json
import sys

path = sys.argv[1]

with open(path, "r") as f:
    data = json.load(f)

items = data.get("data", {}).get("items", [])

new_entry = {
    "id": "ipad",
    "url_path": "ipad",
    "require_admin": False,
    "show_in_sidebar": True,
    "icon": "mdi:tablet",
    "title": "iPad",
    "mode": "storage"
}

items.append(new_entry)
data["data"]["items"] = items

with open(path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Registered 'ipad' dashboard in {path}")
PYEOF2
  fi
else
  # Create lovelace_dashboards from scratch
  python3 -c "
import json
data = {
    'version': 1,
    'minor_version': 1,
    'key': 'lovelace_dashboards',
    'data': {
        'items': [
            {
                'id': 'ipad',
                'url_path': 'ipad',
                'require_admin': False,
                'show_in_sidebar': True,
                'icon': 'mdi:tablet',
                'title': 'iPad',
                'mode': 'storage'
            }
        ]
    }
}
with open('${DASHBOARDS_FILE}', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('Created lovelace_dashboards with ipad entry')
"
fi

# ---------- theme config ----------

cat << 'EOF'

Done. Next steps:

1. If running HA in Docker, the config dir inside the container is /config.
   You may need to run this script targeting the Docker volume mount point:

     ./inject-dashboard.sh /path/to/docker/ha-config

2. Restart Home Assistant (or reload dashboards from Developer Tools).

3. Access the dashboard at:
     http://localhost:8123/lovelace-ipad/main

4. For the dark theme, add this to your configuration.yaml if not already present:

     frontend:
       themes: !include_dir_merge_named themes/

   Or set the default theme in your HA profile to a dark theme.

5. For the DMX placeholder sensors, add these to configuration.yaml:

     template:
       - sensor:
           - name: "DMX Status"
             unique_id: dmx_status
             state: "Offline"
             icon: mdi:led-strip-variant
           - name: "DMX Universe 1"
             unique_id: dmx_universe_1
             state: "N/A"
             icon: mdi:numeric-1-circle
           - name: "DMX Universe 2"
             unique_id: dmx_universe_2
             state: "N/A"
             icon: mdi:numeric-2-circle

6. Required HACS frontend cards:
   - custom:layout-card (layout-card)
   - custom:mushroom-light-card (mushroom)
   - custom:mushroom-title-card (mushroom)

   Install via HACS > Frontend, or add these repos manually.

7. For kiosk mode on iPad (hide sidebar/header), install:
   - kiosk-mode (HACS)
   Then add to your dashboard YAML:
     kiosk_mode:
       kiosk: true

EOF
