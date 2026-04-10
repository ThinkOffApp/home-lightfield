# home-lightfield

Full-apartment programmable lighting system with reactive art installations. Replaces Resolume with a custom control stack: Art-Net/DMX over ethernet, camera-driven animations, and Home Assistant integration.

## Hardware

### DMX Fixtures (Art-Net over ethernet)
- **110m RGBW LED strip** — snakes through all rooms, ceiling, and mid-level windows. Hundreds of DMX channels with complex pixel mapping (existing Resolume mapping to be imported)
- **2x 5x5 RGB pixel blinders** — mounted in windows facing the park. Currently running eye-tracking/blinking animations visible from the street
- **6 DMX spots** — aimed at 3 mirror balls for atmospheric lighting

### Smart Home
- **Philips Hue** — general room lighting (native HA integration)
- **Sonoff RF Bridge R2** — 433MHz curtain motor control
- **2x cameras + 1 doorbell camera** — interior person tracking and entrance monitoring

### Infrastructure
- **Mac mini** — runs Home Assistant, OLA (Art-Net output), animation engine. Ethernet port on Art-Net network, wifi for internet
- **Dell laptop** — secondary compute, ethernet available
- **Network topology:** 3 separate ethernet networks (internet, Art-Net/DMX, Dante/audio)

## Architecture

```
Cameras ──► Frigate (CV/AI) ──► Home Assistant ──► Automation Logic
                                      │
                                      ▼
                              Animation Engine
                                      │
                                      ▼
                                 OLA (Art-Net)
                                      │
                              ┌───────┼───────┐
                              ▼       ▼       ▼
                          LED Strip  Blinders  Spots
```

## Features

### 1. Pixel Mapper
- Import existing Resolume pixel mapping for the 110m strip
- Visual editor: trace strip path on floor plan, auto-assign DMX addresses
- 5x5 blinder grid editor with channel assignment
- Spot fixture profiles

### 2. Animation Engine
- **LED strip person-following:** Frigate detects people via interior cameras, maps position to strip segments, creates follow-spot pools of light
- **5x5 blinder animations:** eye tracking, blinking, reactive patterns. Outdoor camera watches the park/street, eyes follow pedestrians and cars
- **Generative patterns:** time-of-day, weather-reactive, audio-reactive (Dante network available)
- **Scene system:** save/recall full-venue lighting states

### 3. Home Assistant Integration
- **Doorbell:** color indicator on LED strip when person approaches. Persistent segment color when package is left
- **Curtains:** Sonoff RF Bridge R2 control via HA
- **Hue:** coordinated with DMX for full-room scenes
- **Presence:** Frigate zones trigger lighting automations

### 4. Web Dashboard
- Real-time preview of all fixtures
- Animation parameter controls
- Camera feeds with overlay showing detected objects and mapped zones
- Mobile-friendly for control from any device

## Tech Stack

- **Home Assistant** — automation hub, device integrations
- **Frigate** — local AI object detection (person, car, package)
- **OLA (Open Lighting Architecture)** — Art-Net/sACN output to DMX network
- **Node.js / Python** — animation engine and web dashboard
- **Art-Net** — UDP protocol over dedicated ethernet network

## Setup

TODO: Installation and configuration instructions.

## Resolume Migration

The existing Resolume project contains pixel mapping data for the 110m strip and blinder fixtures. The migration tool will:

1. Read Resolume's fixture mapping (XML/JSON export or direct project file parsing)
2. Convert to home-lightfield's internal format
3. Preserve DMX universe/channel assignments
4. Generate a visual preview for verification

## License

AGPL-3.0
