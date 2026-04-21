"""
Autonomous camera-driven blinder animation daemon.

Monitors HA cameras via YOLO object detection, maps detections to
eye animations, and drives the blinders via Art-Net DMX.

Also serves an HTTP status API on port 8898 for the preview dashboard.

Usage:
    python3 detector.py                  # run with camera_config.json
    python3 detector.py --config X.json  # custom config
    python3 detector.py --dry-run        # no DMX output, just detect + log
"""

import json
import time
import io
import sys
import os
import re
import socket
import threading
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import asyncio
import requests
from PIL import Image
import numpy as np
from astral import LocationInfo
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder
import websockets
from astral.sun import sun
from ultralytics import YOLO

# Load .env file if present (for HA_TOKEN etc.)
_env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(__file__))
from grid import Grid
from expressions import *
from sequences import *
from engine import (
    build_dmx_frames, send_frame, blackout as dmx_blackout,
    _build_artnet_packet, BRIGHTNESS, FPS,
    RIGHT_NODE, RIGHT_UNIVERSE, LEFT_NODE, LEFT_UNIVERSE,
    BROADCAST_ADDR, _CHAIN_NODE, _CHAIN_UNIVERSES,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'camera_config.json')

def load_config(path=None):
    p = path or CONFIG_PATH
    with open(p) as f:
        return json.load(f)

def save_config(cfg, path=None):
    """Save config to disk, stripping ha_token (keep secrets in .env only)."""
    p = path or CONFIG_PATH
    clean = dict(cfg)
    clean['ha_token'] = ''  # never write token to disk
    with open(p, 'w') as f:
        json.dump(clean, f, indent=2)

# ---------------------------------------------------------------------------
# Sun schedule
# ---------------------------------------------------------------------------

def parse_sun_offset(spec, sun_times):
    """Parse 'sunset-10m', 'sunrise+30m', or '22:00' into a datetime."""
    m = re.match(r'(sunrise|sunset)([+-]\d+)m', spec)
    if m:
        event = m.group(1)
        offset_min = int(m.group(2))
        base = sun_times[event]
        return base + datetime.timedelta(minutes=offset_min)
    # Fixed time HH:MM
    m2 = re.match(r'(\d{1,2}):(\d{2})', spec)
    if m2:
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        return now.replace(hour=int(m2.group(1)), minute=int(m2.group(2)),
                           second=0, microsecond=0)
    return None


def get_sun_times(lat, lon):
    """Get today's sunrise/sunset for Helsinki (or configured location)."""
    loc = LocationInfo(latitude=lat, longitude=lon)
    s = sun(loc.observer, date=datetime.date.today(),
            tzinfo=datetime.datetime.now().astimezone().tzinfo)
    return {
        'sunrise': s['sunrise'],
        'sunset': s['sunset'],
        'dawn': s['dawn'],
        'dusk': s['dusk'],
    }


def is_active_now(cfg, sun_times):
    """Check if current time falls within any configured schedule window."""
    if cfg.get('always_on'):
        return True
    now = datetime.datetime.now(datetime.timezone.utc).astimezone()
    for window in cfg.get('schedule', []):
        start = parse_sun_offset(window['start'], sun_times)
        end = parse_sun_offset(window['end'], sun_times)
        if start and end:
            # Handle overnight windows (end < start means crosses midnight)
            if end < start:
                if now >= start or now <= end:
                    return True
            else:
                if start <= now <= end:
                    return True
    return False

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

_weather_cache = {'data': None, 'fetched_at': 0}

def fetch_weather(lat, lon):
    """Fetch current weather from Open-Meteo (free, no API key)."""
    now = time.time()
    if _weather_cache['data'] and now - _weather_cache['fetched_at'] < 900:
        return _weather_cache['data']
    try:
        url = (f'https://api.open-meteo.com/v1/forecast'
               f'?latitude={lat}&longitude={lon}&current_weather=true')
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()['current_weather']
        # Map WMO weather codes to mood categories
        code = data.get('weathercode', 0)
        if code <= 1:
            mood = 'clear'
        elif code <= 3:
            mood = 'cloudy'
        elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
            mood = 'rain'
        elif code in (71, 73, 75, 77, 85, 86):
            mood = 'snow'
        elif code in (95, 96, 99):
            mood = 'storm'
        elif code in (45, 48):
            mood = 'fog'
        else:
            mood = 'cloudy'
        result = {
            'temperature': data.get('temperature'),
            'windspeed': data.get('windspeed'),
            'weathercode': code,
            'mood': mood,
        }
        _weather_cache['data'] = result
        _weather_cache['fetched_at'] = now
        return result
    except Exception as e:
        print(f'Weather fetch failed: {e}')
        return _weather_cache['data'] or {'mood': 'clear', 'temperature': 0}

# ---------------------------------------------------------------------------
# Weather mood animations
# ---------------------------------------------------------------------------

# Color sets for weather moods
MOOD_COLORS = {
    'thinkoff': THINKOFF_PALETTE,
    'thinkoff_muted': [
        (106, 83, 117), (116, 99, 123), (120, 104, 124),
        (109, 35, 120), (96, 75, 105),
    ],
    'blue': [
        (20, 40, 120), (40, 80, 180), (60, 120, 220),
        (96, 165, 250), (140, 200, 255),
    ],
    'ice': [
        (200, 220, 255), (180, 200, 240), (220, 240, 255),
        (255, 255, 255), (160, 190, 230),
    ],
    'pink_fuchsia': list(PINK_FUCHSIA),
    'white_dim': [
        (30, 30, 35), (40, 40, 45), (50, 50, 55),
        (60, 60, 65), (45, 45, 50),
    ],
}

def get_weather_sequence(mood_name, moods_cfg):
    """Build an animation generator for the current weather mood."""
    mood = moods_cfg.get(mood_name, moods_cfg.get('clear', {}))
    anim = mood.get('animation', 'breathe')
    color_key = mood.get('colors', 'thinkoff')
    speed = mood.get('speed', 0.5)
    colors = MOOD_COLORS.get(color_key, THINKOFF_PALETTE)
    # Much slower — breathe should take 30-60s per cycle, not 8s
    dur = 60.0 / max(0.1, speed)

    if anim == 'breathe':
        c_a = colors[0] if colors else TK_CORE
        c_b = colors[-1] if colors else TK_EDGE
        return breathe(dur, c_a, c_b)
    elif anim == 'rain':
        return color_rain(dur, colors)
    elif anim == 'kaleidoscope':
        return kaleidoscope(dur, colors)
    elif anim == 'pinwheel':
        return pinwheel(dur, colors)
    elif anim == 'plasma':
        return plasma(dur, colors)
    elif anim == 'ripple':
        return ripple(dur, colors)
    else:
        return breathe(dur, TK_CORE, TK_EDGE)

# ---------------------------------------------------------------------------
# Camera snapshot
# ---------------------------------------------------------------------------

def fetch_snapshot(ha_url, ha_token, entity_id):
    """Fetch camera snapshot from HA proxy API. Returns PIL Image or None."""
    url = f'{ha_url}/api/camera_proxy/{entity_id}'
    headers = {'Authorization': f'Bearer {ha_token}'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    except Exception as e:
        print(f'Snapshot fetch failed: {e}')
        return None


# ---------------------------------------------------------------------------
# WebRTC camera frame grabber (for Nest cameras that don't support snapshots)
# ---------------------------------------------------------------------------

def _fix_nest_sdp(sdp):
    """Fix Nest's non-standard SDP candidate lines for aiortc.
    Nest omits the 'component' field. Standard ICE candidates have:
      candidate:foundation component protocol priority address port
    Nest sends:
      candidate: foundation protocol priority address port
    We insert component=1 after foundation."""
    lines = []
    for line in sdp.split('\r\n'):
        if line.startswith('a=candidate:'):
            # a=candidate: 1 udp 2113939711 ... -> a=candidate:1 1 udp 2113939711 ...
            after = line[len('a=candidate:'):]
            parts = after.strip().split()
            if len(parts) >= 2 and parts[1] in ('udp', 'tcp', 'ssltcp'):
                # Missing component - insert '1' after foundation
                parts.insert(1, '1')
                line = 'a=candidate:' + ' '.join(parts)
        lines.append(line)
    return '\r\n'.join(lines)


class WebRTCFrameGrabber:
    """Connects to HA Nest camera via WebRTC, captures latest frame."""

    def __init__(self):
        self._frame = None
        self._lock = threading.Lock()
        self._pc = None
        self._connected = False
        self._loop = None
        self._thread = None

    @property
    def latest_frame(self):
        with self._lock:
            return self._frame

    @property
    def connected(self):
        return self._connected

    def start(self, ha_url, ha_token, entity_id):
        """Start WebRTC connection in background thread."""
        self._thread = threading.Thread(
            target=self._run, args=(ha_url, ha_token, entity_id),
            daemon=True)
        self._thread.start()

    def _run(self, ha_url, ha_token, entity_id):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(
            self._connect(ha_url, ha_token, entity_id))

    async def _connect(self, ha_url, ha_token, entity_id):
        ws_url = ha_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/api/websocket'

        while True:
            try:
                await self._do_connect(ws_url, ha_token, entity_id)
            except Exception as e:
                print(f'WebRTC connect error: {e}')
                self._connected = False
            await asyncio.sleep(5)  # retry after 5s

    async def _do_connect(self, ws_url, ha_token, entity_id):
        from aiortc import MediaStreamTrack
        import av

        async with websockets.connect(ws_url) as ws:
            msg = json.loads(await ws.recv())  # auth_required
            await ws.send(json.dumps({'type': 'auth', 'access_token': ha_token}))
            msg = json.loads(await ws.recv())  # auth_ok
            if msg.get('type') != 'auth_ok':
                print(f'HA auth failed: {msg}')
                return

            pc = RTCPeerConnection()
            self._pc = pc

            @pc.on('track')
            def on_track(track):
                if track.kind == 'video':
                    asyncio.ensure_future(self._consume_track(track))

            # Nest requires audio + video + datachannel
            pc.addTransceiver('audio', direction='recvonly')
            pc.addTransceiver('video', direction='recvonly')
            pc.createDataChannel('dataSendChannel')

            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)

            await ws.send(json.dumps({
                'id': 1,
                'type': 'camera/webrtc/offer',
                'entity_id': entity_id,
                'offer': pc.localDescription.sdp
            }))

            # Wait for answer SDP from HA events
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                msg = json.loads(raw)
                if msg.get('id') == 1:
                    if msg.get('event', {}).get('answer'):
                        fixed_sdp = _fix_nest_sdp(msg['event']['answer'])
                        answer = RTCSessionDescription(
                            sdp=fixed_sdp, type='answer')
                        await pc.setRemoteDescription(answer)
                        self._connected = True
                        print(f'WebRTC connected to {entity_id}')
                        break
                    elif msg.get('event', {}).get('type') == 'error':
                        raise Exception(msg['event'].get('message', 'unknown'))

            # Keep connection alive until it drops
            while pc.connectionState in ('connected', 'new', 'connecting'):
                await asyncio.sleep(1)

            print('WebRTC connection ended')
            self._connected = False

    async def _consume_track(self, track):
        """Read video frames and store latest as PIL Image."""
        frame_count = 0
        while True:
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=5)
                # Convert av.VideoFrame to PIL Image
                img = frame.to_image()
                with self._lock:
                    self._frame = img
                frame_count += 1
                if frame_count == 1:
                    print(f'First WebRTC frame: {img.size}')
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    def stop(self):
        self._connected = False
        if self._pc:
            asyncio.run_coroutine_threadsafe(self._pc.close(), self._loop)


_frame_grabber = None

def get_frame_grabber():
    global _frame_grabber
    if _frame_grabber is None:
        _frame_grabber = WebRTCFrameGrabber()
    return _frame_grabber


def fetch_webrtc_frame(ha_url, ha_token, entity_id):
    """Get latest frame from WebRTC stream. Starts connection if needed."""
    grabber = get_frame_grabber()
    if not grabber.connected:
        print(f'Starting WebRTC stream to {entity_id}...')
        grabber.start(ha_url, ha_token, entity_id)
        # Wait up to 15s for first frame
        for _ in range(30):
            time.sleep(0.5)
            if grabber.latest_frame is not None:
                break
    return grabber.latest_frame

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_model = None

def get_model():
    global _model
    if _model is None:
        _model = YOLO('yolov8m.pt')
    return _model


# Only detect classes that make sense for an outdoor park/street scene
RELEVANT_CLASSES = {
    'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
    'dog', 'cat', 'bird', 'horse',
    'skateboard', 'umbrella', 'backpack', 'handbag', 'suitcase',
    'sports ball', 'kite', 'frisbee',
}

# Living things are reported even when static (a person standing still is interesting)
LIVING = {'person', 'dog', 'cat', 'bird', 'horse'}


def detect_objects(image, min_confidence=0.25, min_area=0.0005):
    """Run YOLO detection on PIL Image. Returns list of detections."""
    model = get_model()
    results = model(image, verbose=False, imgsz=1280)
    detections = []
    img_w, img_h = image.size
    img_area = img_w * img_h

    for r in results:
        for box in r.boxes:
            conf = float(box.conf[0])
            if conf < min_confidence:
                continue
            cls_id = int(box.cls[0])
            label = model.names[cls_id]
            if label not in RELEVANT_CLASSES:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            box_area = (x2 - x1) * (y2 - y1) / img_area
            if box_area < min_area:
                continue
            cx = (x1 + x2) / 2 / img_w  # normalized 0-1
            cy = (y1 + y2) / 2 / img_h
            detections.append({
                'label': label,
                'confidence': round(conf, 3),
                'bbox': [round(x1), round(y1), round(x2), round(y2)],
                'center': [round(cx, 3), round(cy, 3)],
                'area': round(box_area, 4),
            })

    detections.sort(key=lambda d: d['confidence'], reverse=True)
    return detections


# ---------------------------------------------------------------------------
# Motion tracker - distinguish static vs moving objects
# ---------------------------------------------------------------------------

class MotionTracker:
    """Tracks individual objects across frames using spatial proximity.

    Each tracked object has: id, label, position history, moving flag.
    Objects are matched between frames by class + nearest position.
    An object is 'moving' only if it shows consistent directional travel
    over 4+ frames (not random YOLO bbox jitter).
    """

    MATCH_RADIUS = 0.25   # max distance to match same object across frames
    HISTORY_LEN = 6       # frames of position history
    MIN_DISPLACEMENT = 0.08  # minimum start-to-end distance for "moving"
    MIN_DIRECTION_RATIO = 0.4  # displacement/path ratio (1=straight, 0=jitter)

    def __init__(self):
        self._objects = []  # [{id, label, positions: [(cx,cy,t),...], moving}]
        self._next_id = 0

    def _match_objects(self, detections):
        """Match current detections to tracked objects using Hungarian-lite."""
        matched = {}  # det_idx -> obj_idx
        used_objs = set()

        # Build candidate pairs sorted by distance
        pairs = []
        for di, det in enumerate(detections):
            for oi, obj in enumerate(self._objects):
                if obj['label'] != det['label']:
                    continue
                ox, oy = obj['positions'][-1][:2]
                d = ((det['center'][0] - ox)**2 + (det['center'][1] - oy)**2)**0.5
                if d < self.MATCH_RADIUS:
                    pairs.append((d, di, oi))
        pairs.sort()

        for d, di, oi in pairs:
            if di in matched or oi in used_objs:
                continue
            matched[di] = oi
            used_objs.add(oi)

        return matched

    def _is_moving(self, positions):
        """Determine if position history shows real directional movement."""
        if len(positions) < 4:
            return False

        x0, y0 = positions[0][0], positions[0][1]
        xn, yn = positions[-1][0], positions[-1][1]
        displacement = ((xn - x0)**2 + (yn - y0)**2) ** 0.5

        if displacement < self.MIN_DISPLACEMENT:
            return False

        # Calculate path length
        path_len = 0
        for i in range(1, len(positions)):
            dx = positions[i][0] - positions[i-1][0]
            dy = positions[i][1] - positions[i-1][1]
            path_len += (dx*dx + dy*dy) ** 0.5

        if path_len < 0.01:
            return False

        ratio = displacement / path_len
        return ratio > self.MIN_DIRECTION_RATIO

    def update(self, detections):
        """Match detections to tracked objects and set moving flag."""
        now = time.time()
        matched = self._match_objects(detections)

        for di, det in enumerate(detections):
            cx, cy = det['center']
            if di in matched:
                # Update existing tracked object
                obj = self._objects[matched[di]]
                obj['positions'].append((cx, cy, now))
                obj['positions'] = obj['positions'][-self.HISTORY_LEN:]
                obj['moving'] = self._is_moving(obj['positions'])
                det['moving'] = obj['moving']
            else:
                # New object — create tracker, default to static
                obj = {
                    'id': self._next_id,
                    'label': det['label'],
                    'positions': [(cx, cy, now)],
                    'moving': False,
                }
                self._next_id += 1
                self._objects.append(obj)
                det['moving'] = False

        # Remove objects not seen for 5 seconds
        self._objects = [
            o for o in self._objects
            if now - o['positions'][-1][2] < 5
        ]

        return detections


_motion_tracker = MotionTracker()


def draw_detections(image, detections):
    """Draw bounding boxes on image. Returns annotated PIL Image."""
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(image)
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        color = (0, 255, 100)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{det['label']} {det['confidence']:.0%}"
        draw.text((x1 + 4, y1 + 2), label, fill=color)
    return image

# ---------------------------------------------------------------------------
# Detection-to-animation mapping
# ---------------------------------------------------------------------------

def pick_animation(detections, cfg, weather_mood, last_detection_time):
    """Pick the best animation based on detections, mappings, and weather.
    Only moving objects trigger reactions. Static objects are ignored
    unless in idle mode."""
    mappings = cfg.get('mappings', {})
    idle_timeout = cfg.get('idle_timeout_sec', 10)
    now = time.time()

    # React to moving objects + static living things
    interesting = [d for d in detections
                   if d.get('moving', False) or d['label'] in LIVING]

    if not interesting:
        if now - last_detection_time > idle_timeout:
            nothing_cfg = mappings.get('nothing', {})
            anim_name = nothing_cfg.get('animation', 'blackout')
            if anim_name == 'weather_mood':
                return 'weather_mood', None, None
            return anim_name, None, None
        return None, None, None  # keep current animation

    # Pick highest priority interesting detection
    best = None
    best_priority = 999
    best_anim = 'idle_scan'
    for det in interesting:
        label = det['label']
        m = mappings.get(label, mappings.get('default', {}))
        p = m.get('priority', 99)
        if p < best_priority:
            best_priority = p
            best = det
            best_anim = m.get('animation', 'idle_scan')

    if best is None:
        return None, None, None

    return best_anim, best['center'], best


_hypnotic_cycle_idx = 0

def build_animation_sequence(anim_name, center, cfg, weather_mood):
    """Build an animation generator from name + detection position."""
    global _hypnotic_cycle_idx
    moods_cfg = cfg.get('weather_moods', {})

    if anim_name == 'track' and center:
        x_norm, y_norm = center
        # Build a smooth 1-second hold so eye moves smoothly to new positions
        look = look_at_xy(x_norm, y_norm, iris_color=TK_CORE)
        return [(look, look, 50)] * 20
    elif anim_name == 'love':
        return list(love())
    elif anim_name == 'surprise':
        return list(surprise())
    elif anim_name == 'idle_scan':
        return list(idle_scan(30.0, iris_color=TK_CORE))
    elif anim_name == 'weather_mood':
        return list(get_weather_sequence(weather_mood, moods_cfg))
    elif anim_name == 'blackout':
        g = Grid()
        return [(g, g, 100)]
    elif anim_name == 'hypnotize':
        return list(hypnotize(12.0, TK_CORE))
    elif anim_name == 'ripple':
        return list(ripple(12.0, THINKOFF_PALETTE))
    elif anim_name == 'plasma':
        return list(plasma(12.0, PINK_FUCHSIA))
    elif anim_name == 'pinwheel':
        return list(pinwheel(12.0, THINKOFF_PALETTE))
    elif anim_name == 'kaleidoscope':
        return list(kaleidoscope(12.0, THINKOFF_PALETTE))
    elif anim_name == 'breathe':
        return list(breathe(30.0, TK_CORE, TK_MAGENTA))
    elif anim_name == 'hypnotic_mix':
        # Cycle through hypnotic animations, each for ~15s, then next call gets next
        anims = [
            lambda: hypnotize(15.0, TK_MAGENTA),
            lambda: plasma(15.0, PINK_FUCHSIA),
            lambda: ripple(15.0, THINKOFF_PALETTE),
            lambda: kaleidoscope(15.0, THINKOFF_PALETTE),
            lambda: pinwheel(15.0, THINKOFF_PALETTE),
            lambda: hypnotize(15.0, TK_CORE),
        ]
        seq = list(anims[_hypnotic_cycle_idx % len(anims)]())
        _hypnotic_cycle_idx += 1
        return seq
    else:
        return list(idle_scan(5.0))

# ---------------------------------------------------------------------------
# Shared state (for HTTP API)
# ---------------------------------------------------------------------------

class DetectorState:
    def __init__(self):
        self.lock = threading.Lock()
        self.detections = []
        self.active_animation = 'idle'
        self.is_active = False
        self.weather = {}
        self.sun_times = {}
        self.snapshot_jpeg = None
        self.browser_frame = None
        self.annotated_jpeg = None
        self.frame_size = None
        self.uptime_start = time.time()
        self.frames_sent = 0
        self.last_detection_time = 0
        self.config = {}
        self.pending_message = None  # text to scroll on blinders
        # Live grid state for preview (what the blinders are actually showing)
        self.current_left_grid = None   # 5x5 list of [r,g,b]
        self.current_right_grid = None

    def to_dict(self):
        with self.lock:
            sun_str = {}
            for k, v in self.sun_times.items():
                if hasattr(v, 'strftime'):
                    sun_str[k] = v.strftime('%H:%M')
                else:
                    sun_str[k] = str(v)
            return {
                'detections': self.detections,
                'active_animation': self.active_animation,
                'is_active': self.is_active,
                'weather': self.weather,
                'sun_times': sun_str,
                'uptime_sec': round(time.time() - self.uptime_start),
                'frames_sent': self.frames_sent,
                'camera': self.config.get('camera_entity', ''),
                'schedule': self.config.get('schedule', []),
                'always_on': self.config.get('always_on', False),
                'frame_size': self.frame_size,
                'left_grid': self.current_left_grid,
                'right_grid': self.current_right_grid,
            }

STATE = DetectorState()

# ---------------------------------------------------------------------------
# HTTP API (port 8898)
# ---------------------------------------------------------------------------

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress access logs

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/status':
            data = json.dumps(STATE.to_dict()).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)

        elif path == '/snapshot':
            with STATE.lock:
                jpeg = STATE.annotated_jpeg or STATE.snapshot_jpeg
            if jpeg:
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(jpeg)
            else:
                self.send_response(204)
                self._cors()
                self.end_headers()

        elif path == '/config':
            data = json.dumps(STATE.config).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)

        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/frame':
            # Receive a JPEG frame from the browser (1080p WebRTC capture)
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                with STATE.lock:
                    STATE.browser_frame = body
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif path == '/message':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                text = data.get('text', '')
                color = data.get('color', None)  # optional [r,g,b]
                with STATE.lock:
                    STATE.pending_message = {
                        'text': text,
                        'color': tuple(color) if color else TK_CORE,
                    }
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'text': text}).encode())
            except Exception as e:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif path == '/config':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                new_cfg = json.loads(body)
                STATE.config.update(new_cfg)
                save_config(STATE.config)
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self.send_response(400)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()


def start_api_server(port=8898):
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f'API server on http://localhost:{port}')
    return server

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    config_path = CONFIG_PATH
    dry_run = '--dry-run' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    if '--config' in sys.argv:
        idx = sys.argv.index('--config')
        config_path = sys.argv[idx + 1]

    cfg = load_config(config_path)
    STATE.config = cfg

    ha_url = cfg['ha_url']
    ha_token = os.environ.get('HA_TOKEN') or cfg.get('ha_token', '')
    camera = cfg['camera_entity']
    lat = cfg['location']['lat']
    lon = cfg['location']['lon']
    poll_sec = cfg.get('poll_interval_sec', 1.5)

    if not ha_token:
        print('ERROR: ha_token not set in camera_config.json')
        print('Create a long-lived access token in HA:')
        print('  Settings > Security > Long-lived access tokens')
        sys.exit(1)

    # Start HTTP API
    start_api_server()

    # Setup Art-Net socket
    sock = None
    if not dry_run:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind(('0.0.0.0', 0))
        except OSError:
            pass
        print(f'Art-Net socket ready (dry_run={dry_run})')

    # Load YOLO model
    print('Loading YOLO model...')
    get_model()
    print('Model loaded.')

    # Sun times (recalculate daily)
    sun_date = None
    sun_times = {}

    # Weather
    weather = fetch_weather(lat, lon)
    weather_mood = weather.get('mood', 'clear') if weather else 'clear'

    last_detection_time = time.time()

    # Safety: prevent overheating - blinders auto-off after max_on_minutes
    blinders_on_since = None  # timestamp when blinders last turned on
    cooldown_until = 0  # timestamp when cooldown ends

    print(f'Camera: {camera}')
    print(f'Location: {lat}, {lon} (Helsinki)')
    print(f'Weather: {weather_mood}')
    print(f'Dry run: {dry_run}')

    # -------------------------------------------------------------------
    # Art-Net playback thread: runs at 25fps independent of YOLO
    # -------------------------------------------------------------------
    _playback_lock = threading.Lock()
    _playback_sequence = []  # current animation frames
    _playback_idx = 0
    _playback_anim = 'idle'
    _playback_active = True  # whether blinders should be on
    _playback_brightness = cfg.get('brightness', BRIGHTNESS)
    _playback_stop = False

    def artnet_playback():
        nonlocal _playback_sequence, _playback_idx, _playback_stop
        frame_interval = 1.0 / FPS
        last_dmx = None

        while not _playback_stop:
            with _playback_lock:
                seq = _playback_sequence
                idx = _playback_idx
                active = _playback_active
                br = _playback_brightness

            if not active or not seq:
                # Send blackout at low rate to keep nodes from timeout-blinking
                if sock and not dry_run:
                    g = Grid()
                    dmx_l, dmx_r = build_dmx_frames(g, g, 0)
                    send_frame(sock, dmx_l, dmx_r)
                black = [[[0, 0, 0] for _ in range(5)] for _ in range(5)]
                with STATE.lock:
                    STATE.current_left_grid = black
                    STATE.current_right_grid = black
                time.sleep(0.2)
                continue

            if idx < len(seq):
                left_grid, right_grid, frame_ms = seq[idx]
                left_dmx, right_dmx = build_dmx_frames(left_grid, right_grid, br)
                last_dmx = (left_dmx, right_dmx)
                if sock and not dry_run:
                    send_frame(sock, left_dmx, right_dmx)
                    with STATE.lock:
                        STATE.frames_sent += 1
                # Expose actual grid state to preview (applying brightness)
                with STATE.lock:
                    STATE.current_left_grid = [
                        [[int(c * br) for c in left_grid.pixels[y][x]]
                         for x in range(5)] for y in range(5)
                    ]
                    STATE.current_right_grid = [
                        [[int(c * br) for c in right_grid.pixels[y][x]]
                         for x in range(5)] for y in range(5)
                    ]

                with _playback_lock:
                    _playback_idx += 1
                    if _playback_idx >= len(_playback_sequence):
                        # Loop loopable ambient animations
                        if _playback_anim in ('weather_mood', 'breathe',
                                              'idle_scan', 'blackout',
                                              'hypnotize', 'ripple', 'plasma',
                                              'pinwheel', 'kaleidoscope'):
                            _playback_idx = 0
                        elif _playback_anim == 'hypnotic_mix':
                            # Signal main loop to rebuild with next anim in cycle
                            _playback_idx = -1
                        # For one-shot anims, keep last frame
            elif last_dmx:
                # Sequence ended, keep sending last frame to prevent timeout
                if sock and not dry_run:
                    send_frame(sock, last_dmx[0], last_dmx[1])

            time.sleep(frame_interval)

    playback_thread = threading.Thread(target=artnet_playback, daemon=True)
    playback_thread.start()
    print(f'Art-Net playback thread started ({FPS}fps)')

    def set_animation(name, sequence, brightness=None):
        nonlocal _playback_sequence, _playback_idx, _playback_anim
        nonlocal _playback_brightness
        with _playback_lock:
            _playback_sequence = sequence
            _playback_idx = 0
            _playback_anim = name
            if brightness is not None:
                _playback_brightness = brightness
        with STATE.lock:
            STATE.active_animation = name

    def set_playback_active(active):
        nonlocal _playback_active, _playback_brightness
        with _playback_lock:
            _playback_active = active
            # Refresh brightness from current config each cycle
            _playback_brightness = cfg.get('brightness', BRIGHTNESS)

    print('Starting detection loop...')

    try:
        while True:
            loop_start = time.time()

            # Recalculate sun times daily
            today = datetime.date.today()
            if sun_date != today:
                sun_times = get_sun_times(lat, lon)
                sun_date = today
                print(f'Sun times: rise={sun_times["sunrise"].strftime("%H:%M")} '
                      f'set={sun_times["sunset"].strftime("%H:%M")}')
                with STATE.lock:
                    STATE.sun_times = sun_times

            # Refresh weather every 15 min
            weather = fetch_weather(lat, lon)
            weather_mood = weather.get('mood', 'clear') if weather else 'clear'
            with STATE.lock:
                STATE.weather = weather or {}

            # Check schedule
            cfg = STATE.config
            active = is_active_now(cfg, sun_times)
            with STATE.lock:
                STATE.is_active = active

            if not active:
                set_playback_active(False)
                blinders_on_since = None
                with STATE.lock:
                    STATE.active_animation = 'off (outside schedule)'
            else:
                set_playback_active(True)

            # Fetch camera snapshot
            camera = cfg.get('camera_entity', camera)
            ha_url = cfg.get('ha_url', ha_url)
            ha_token = os.environ.get('HA_TOKEN') or cfg.get('ha_token', '')

            image = None
            with STATE.lock:
                browser_jpeg = STATE.browser_frame
                if browser_jpeg:
                    STATE.browser_frame = None
            if browser_jpeg:
                try:
                    image = Image.open(io.BytesIO(browser_jpeg))
                except Exception:
                    pass
            if image is None:
                image = fetch_webrtc_frame(ha_url, ha_token, camera)
            if image is None:
                time.sleep(poll_sec)
                continue

            # Save snapshot for API
            buf = io.BytesIO()
            image.save(buf, format='JPEG', quality=70)
            with STATE.lock:
                STATE.snapshot_jpeg = buf.getvalue()

            # Detect objects
            min_conf = cfg.get('min_confidence', 0.25)
            min_area = cfg.get('min_area', 0.0005)
            detections = detect_objects(image, min_conf, min_area)
            _motion_tracker.update(detections)

            if detections and verbose:
                summary = ', '.join(f'{d["label"]}:{"M" if d.get("moving") else "S"}' for d in detections)
                print(f'  [{len(detections)}] {summary}')

            moving = [d for d in detections if d.get('moving', False)]
            if moving:
                last_detection_time = time.time()

            moving_dets = [d for d in detections
                           if d.get('moving', False) or d['label'] in LIVING]
            with STATE.lock:
                STATE.detections = moving_dets
                STATE.last_detection_time = last_detection_time
                STATE.frame_size = image.size

            # Draw annotated snapshot
            annotated = image.copy()
            draw_detections(annotated, detections)
            abuf = io.BytesIO()
            annotated.save(abuf, format='JPEG', quality=70)
            with STATE.lock:
                STATE.annotated_jpeg = abuf.getvalue()

            if not active:
                time.sleep(poll_sec)
                continue

            # Safety: overheating protection
            max_on = cfg.get('max_on_minutes', 5) * 60
            cooldown_dur = cfg.get('cooldown_minutes', 10) * 60
            now_ts = time.time()

            if now_ts < cooldown_until:
                set_playback_active(False)
                remaining = int((cooldown_until - now_ts) / 60)
                with STATE.lock:
                    STATE.active_animation = f'cooldown ({remaining}m remaining)'
                time.sleep(poll_sec)
                continue

            if blinders_on_since and (now_ts - blinders_on_since) > max_on:
                print(f'Safety: blinders on for {max_on/60:.0f}m, '
                      f'cooling down for {cooldown_dur/60:.0f}m')
                set_playback_active(False)
                blinders_on_since = None
                cooldown_until = now_ts + cooldown_dur
                with STATE.lock:
                    STATE.active_animation = f'cooldown ({int(cooldown_dur/60)}m)'
                time.sleep(poll_sec)
                continue

            if blinders_on_since is None:
                blinders_on_since = time.time()

            # Check for pending text message
            with STATE.lock:
                msg = STATE.pending_message
                STATE.pending_message = None
            if msg:
                print(f'Scrolling message: {msg["text"]}')
                text_seq = list(scroll_text(msg['text'], msg['color']))
                if text_seq:
                    set_animation(f'text: {msg["text"]}', text_seq,
                                  cfg.get('brightness', BRIGHTNESS))
                    # Wait for text to finish
                    time.sleep(len(text_seq) * 0.15)
                    continue

            # Pick animation based on detections
            anim_name, center, best_det = pick_animation(
                moving_dets, cfg, weather_mood, last_detection_time)

            if anim_name is not None:
                label = anim_name
                if best_det:
                    # Include coarse position in label so eye-track rebuilds
                    # when the tracked object moves to a new grid cell.
                    cx, cy = best_det['center']
                    gx, gy = int(cx * 10), int(cy * 10)
                    label = (f'{anim_name} ({best_det["label"]} '
                             f'{best_det["confidence"]:.0%} {gx},{gy})')

                # Only rebuild animation if it's actually changing, or
                # the playback thread signaled it finished (idx=-1 for
                # hypnotic_mix so we pick the next one in rotation).
                with _playback_lock:
                    current = _playback_anim
                    current_idx = _playback_idx
                loopable = anim_name in ('weather_mood', 'breathe',
                                         'idle_scan', 'blackout',
                                         'hypnotize', 'ripple', 'plasma',
                                         'pinwheel', 'kaleidoscope')
                needs_rebuild = (
                    current != label or
                    current_idx < 0 or
                    (not loopable and anim_name != 'hypnotic_mix')
                )
                if needs_rebuild:
                    seq = build_animation_sequence(
                        anim_name, center, cfg, weather_mood)
                    set_animation(label, seq, cfg.get('brightness', BRIGHTNESS))

            # Detection loop runs as fast as YOLO allows
            elapsed = time.time() - loop_start
            sleep_time = max(0.01, poll_sec - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        _playback_stop = True
        if sock and not dry_run:
            dmx_blackout(sock)
            sock.close()
        print('Detector stopped.')


if __name__ == '__main__':
    main()
