# Temporal Alignment

All data in the NWB files is referenced to a single **session master clock** — the NIDQ DAQ
board (or widefield DAQ board when NIDQ is absent). This is the same clock used by IBL's
Brain-Wide Map pipeline.

---

## IBL Synchronization Architecture

### Background: the full Brain-Wide Map three-tier system

The IBL Brain-Wide Map uses hardware synchronization to align recordings across devices that
each have their own independent clock (typical drift: **10–50 ppm**, which accumulates to
100–300 ms over a one-hour session without correction):

| Tier | Device | Clock rate | Role |
|---|---|---|---|
| 1 | NIDQ DAQ board | ~1 kHz (30,003 Hz in practice) | Session master clock; records all sync signals from external devices |
| 2 | Neuropixels probes | 30 kHz AP / 2.5 kHz LF (independent, drifts) | Neural data; records a copy of sync signals on SYNC channel |
| 3 | Alignment files | — | Maps probe sample indices → session time |

For Brain-Wide Map sessions with Neuropixels probes, IBL's preprocessing:
1. Extracts a shared **1 Hz `imec_sync` square wave** recorded on both NIDQ and all probes
2. Matches those pulses to estimate per-probe clock drift
3. Produces `{probe}.timestamps.npy` — anchor points from which `SpikeSortingLoader.samples2times()`
   interpolates every neural sample to session time (achieved precision: **0.01–0.1 ms**)

### How `imaging.times.npy` is generated

Before this converter runs, IBL's preprocessing pipeline has already aligned widefield
frame timestamps to the session master clock. The pipeline:
1. Records a **frame trigger TTL pulse** on the NIDQ (or widefield DAQ) for every camera frame
   — each rising edge is one acquired frame, already in master-clock time
2. Uses those pulse timestamps directly as `imaging.times.npy`
3. Assigns each timestamp a `channel_id` via `imaging.imagingLightSource.npy`

The result is that `imaging.times.npy` is already in the NIDQ/DAQ clock with no further
alignment needed by this converter.

### Widefield sessions — NIDQ present vs. absent

| Master clock                    | Sync source |
|---------------------------------|---|
| NIDQ board                      | `raw_ephys_data/` → `IblNIDQInterface` |
| NI USB-6356 DAQ board (labcams) | `raw_sync_data/` → `IblWidefieldDAQInterface` |

In `raw_sync_data` widefield sessions the NI USB-6356 serves as the local master clock: it records
the same sync signals as NIDQ (camera TTLs, frame trigger, rotary encoder, audio, Bpod). The pre-extracted
`raw_sync_data/_spikeglx_sync.{channels,times,polarities}.npy` and
`alf/widefield/imaging.times.npy` are all on this DAQ clock.

### All data streams for widefield sessions

| Data stream | Clock source | Alignment status |
|---|---|---|
| `alf/widefield/imaging.times.npy` | NIDQ / DAQ master clock | Pre-aligned by IBL preprocessing from frame trigger TTL pulses |
| DAQ/NIDQ digital events (`_spikeglx_sync.*.npy`) | NIDQ / DAQ master clock | Direct — no conversion needed |
| DAQ/NIDQ analog channels (`.cbin`) | NIDQ / DAQ master clock | Direct — `starting_time=0.0` (recording starts at t=0) |
| Behavioral data (trials, wheel, licks, etc.) | NIDQ / DAQ master clock | Pre-aligned by IBL preprocessing |
| Camera frame times (`_ibl_{camera}Camera.times.npy`) | NIDQ / DAQ master clock | Pre-aligned from camera TTL pulses on NIDQ/DAQ |

### What this converter does

The only alignment step performed here is **wavelength demultiplexing**: splitting the
interleaved `imaging.times.npy` array into two per-wavelength timestamp arrays (470 nm and
405 nm) using `imaging.imagingLightSource.npy`. This is done in
`WidefieldRawNWBConverter.temporally_align_data_interfaces()`, which calls
`WidefieldImagingInterface.get_aligned_timestamps()` on each interface before any data is
written.

---

## Dual-Wavelength Demultiplexing

Raw widefield data alternates between two excitation wavelengths in every other frame.
The actual `channel_id` values (integers) for each wavelength are read from
`alf/widefield/imagingLightSource.properties.htsv` at runtime — in all observed sessions:
`channel_id=2` → 470 nm (calcium), `channel_id=1` → 405 nm (isosbestic).

```
Frame index:   0    1    2    3    4    5   ...
Wavelength:   470  405  470  405  470  405  ...  (order confirmed from .htsv)

imaging.times.npy  → [t0, t1, t2, t3, t4, t5, ...]
imagingLightSource → [ 2,  1,  2,  1,  2,  1, ...]   (channel_id: 2=470 nm, 1=405 nm)

After demux:
  470 nm timestamps → [t0, t2, t4, ...]   → OnePhotonSeriesCalcium
  405 nm timestamps → [t1, t3, t5, ...]   → OnePhotonSeriesIsosbestic
```

Note: `len(imaging.imagingLightSource.npy)` is sometimes 1 greater than
`len(imaging.times.npy)` — the production code and consistency checks both truncate to
`min(len(all_times), len(light_sources))` before filtering. See
[Open Questions](open_questions.md) Q5 for details.

The per-channel sampling rate is `raw_fps / 2` (e.g., 62.5 Hz raw → 31.25 Hz per channel).

---

## Empirical Validation

Checked against the converted NWB file `sub-FD-28_ses-81f90b18_desc-raw_behavior+ophys.nwb`
(widefield-only session, NI USB-6356 master clock):

| Signal | t_start (s) | t_end (s) | Notes |
|---|---|---|---|
| `OnePhotonSeriesCalcium` | 1.4240 | 4000.6900 | ~31.25 Hz; inter-frame interval = 32.02 ms ± 0.015 ms |
| `OnePhotonSeriesIsosbestic` | 1.4400 | 4000.7060 | Offset from Calcium = 16.01 ms ± 0.016 ms ✓ |
| `EventsFrameTrigger` (frame_on) | 1.4240 | 4000.7281 | Matches imaging t_start with **0.00 ms error** ✓ |
| `EventsLeftCamera` | 1.2919 | 4000.7089 | Camera starts slightly before imaging |
| `EventsRotaryEncoder0` | 0.2310 | 4001.4008 | Earliest event — animal moving before imaging begins |
| `TimeSeriesBpod` | 0.0000 | 4001.8000 | `starting_time=0.0`; covers full session |

**Key findings:**
- Imaging timestamps match frame trigger events with **0.00 ms error** ✓
- Isosbestic offset from calcium is exactly **16.01 ms** (one interleaved frame period) ✓
- All signals share the same ~4000 s time base ✓
- `starting_time=0.0` for the DAQ analog channel is consistent with all other signals — the
  master clock starts at t=0 when recording begins (see [Open Questions](open_questions.md) Q2)

---
