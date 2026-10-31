"""Shared configuration and severity rules. No database credentials in source."""
from datetime import datetime, timezone
from pathlib import Path
import math
import json
import os
import tempfile
import threading
import psycopg
from dotenv import load_dotenv

FOLDER = Path(__file__).resolve().parent
load_dotenv(FOLDER / '.env', override=True)
NODES = {'monitor-node1': '192.168.56.21',
         'monitor-node2': '192.168.56.22',
         'monitor-node3': '192.168.56.23'}
RESOURCES = ('cpu', 'ram', 'disk')
DEFAULT_LIMITS = {'cpu': (60, 70, 85), 'ram': (60, 70, 85), 'disk': (60, 75, 90)}
LIMITS = DEFAULT_LIMITS.copy()
_settings_lock = threading.RLock()
LEVELS = ('NORMAL', 'LOW PRIORITY', 'WARNING', 'CRITICAL')
COLORS = dict(zip(LEVELS, ('green', 'yellow', 'orange', 'red')))
INTERVAL, TIMEOUT, FAILURE_LIMIT = 5, 4, 3

def classify(resource, value):
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(f'Invalid {resource} percentage: {value}')
    return LEVELS[sum(value >= limit for limit in LIMITS[resource])]

def availability_severity(status):
    return {'REACHABLE': 'NORMAL', 'RETRYING': 'LOW PRIORITY',
            'UNAVAILABLE': 'CRITICAL'}.get(status, 'UNKNOWN')

def connect(readonly=False, rows=None):
    opts = '-c statement_timeout=10000'
    if readonly:
        opts += ' -c default_transaction_read_only=on'
    return psycopg.connect(connect_timeout=5, autocommit=True,
                           row_factory=rows, options=opts,
                           application_name='proxmox-monitor-v2')

def utcnow():
    return datetime.now(timezone.utc)


THRESHOLD_FILE = FOLDER / 'threshold_settings.json'

def validate_limits(payload):
    if not isinstance(payload, dict) or set(payload) != set(RESOURCES):
        raise ValueError('Provide CPU, RAM and disk boundaries.')
    result = {}
    for resource in RESOURCES:
        values = payload[resource]
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f'{resource.upper()}: provide Low, Warning and Critical boundaries.')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError('Boundaries must be finite numbers.')
        low, warning, critical = map(float, values)
        if not 0 < low < warning < critical <= 100:
            raise ValueError(f'{resource.upper()}: require 0 < Low < Warning < Critical <= 100.')
        result[resource] = (low, warning, critical)
    return result

def refresh_limits():
    try:
        payload = json.loads(THRESHOLD_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError:
        payload = DEFAULT_LIMITS
    current = validate_limits(payload)
    LIMITS.update(current)
    return current

def save_limits(payload):
    current = validate_limits(payload)
    with _settings_lock:
        fd, name = tempfile.mkstemp(prefix='sis-threshold-', suffix='.tmp', dir=FOLDER)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(current, file, indent=2)
                file.flush(); os.fsync(file.fileno())
            os.replace(name, THRESHOLD_FILE)
        finally:
            if os.path.exists(name): os.unlink(name)
        LIMITS.update(current)
    return current

