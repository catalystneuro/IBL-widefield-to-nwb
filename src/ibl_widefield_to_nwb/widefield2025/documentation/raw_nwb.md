# Raw NWB File

**Entry point:** `convert_raw_session()` in `conversion/raw.py`

**Converter:** `WidefieldRawNWBConverter`

**Output filename:** `sub-{subject}_ses-{eid}_desc-raw_behavior+ophys.nwb`

The raw NWB file contains full-resolution widefield imaging frames, synchronization signals
from the DAQ or NIDQ board, and raw behavior video files (linked externally).

---

## Data Flow

```
SOURCE DATA                           INTERFACE                         NWB CONTAINER

raw_widefield_data/
├── imaging.frames.mov         ──→  WidefieldImagingInterface   ──→  OnePhotonSeriesCalcium
├── widefieldChannels.                (dual-wavelength demux)          OnePhotonSeriesIsosbestic
│   wiring.htsv                                                        (nwbfile.acquisition)
└── widefieldEvents.raw.camlog
    + alf/widefield/imaging.*

                  — preferred —
raw_ephys_data/
└── _spikeglx_ephysData_*.     ──→  IblNIDQInterface            ──→  EventsLeftCamera
    nidq.{cbin,meta,ch,                                                EventsRightCamera
    wiring.json}                                                        EventsBodyCamera
                                                                        EventsImecSync
                  — fallback —                                          EventsFrame2ttl
raw_sync_data/                                                          EventsRotaryEncoder0/1
├── _spikeglx_DAQdata.         ──→  IblWidefieldDAQInterface    ──→  EventsAudio
│   {wiring.json,cbin,                                                  EventsFrameTrigger     ← DAQ only
│    meta,ch}                                                           EventsBpodDigital      ← DAQ only
└── _spikeglx_sync.                                                     TimeSeriesBpod
    {channels,polarities,                                               TimeSeriesLaser        ← DAQ only
     times}.npy                                                         TimeSeriesLaserTTL     ← DAQ only
                                                                        (nwbfile.acquisition)

raw_video_data/
├── _iblrig_leftCamera.raw.mp4 ──→  RawVideoInterface (×3)     ──→  ImageSeriesLeftCamera
├── _iblrig_rightCamera.raw.mp4                                         ImageSeriesRightCamera
└── _iblrig_bodyCamera.raw.mp4                                          ImageSeriesBodyCamera
                                                                        (nwbfile.acquisition)

alf/
└── _ibl_passivePeriods.       ──→  SessionEpochsInterface      ──→  epochs (TimeIntervals)
    intervalsTable.csv                                                  (nwbfile.epochs)

alf/widefield/
└── widefieldLandmarks.        ──→  IblWidefieldLandmarksInterface ──→  Localization
    dorsalCortex.json                                                   Landmarks, AtlasRegistration
                                                                        (lab_meta_data)
```

---

## 1. Widefield Imaging

**Interface:** `WidefieldImagingInterface` (one instance per excitation wavelength)

**Source files** (downloaded to `raw_widefield_data/`):

| ONE file | Description |
|---|---|
| `raw_widefield_data/imaging.frames.mov` | Raw video: all wavelengths interleaved (JPEG2000, gray16le) |
| `raw_widefield_data/widefieldChannels.wiring.htsv` | Channel gain, exposure, wavelength per LED |
| `raw_widefield_data/widefieldEvents.raw.camlog` | Camera hardware event log (`#LED:channel,frame,timestamp`) |
| `alf/widefield/imaging.times.npy` | Aligned frame timestamps in seconds (NIDQ clock) |
| `alf/widefield/imaging.imagingLightSource.npy` | Per-frame excitation wavelength index |
| `alf/widefield/imagingLightSource.properties.htsv` | Wavelength properties (nm, LED power) |

**ONE API access:**

```python
one.load_dataset(eid, "imaging.frames", collection="raw_widefield_data", download_only=True)
one.load_dataset(eid, "widefieldChannels.wiring", collection="raw_widefield_data")
one.load_dataset(eid, "widefieldEvents.raw", collection="raw_widefield_data")
one.load_object(eid, "imaging", collection="alf/widefield")
one.load_dataset(eid, "imagingLightSource.properties", collection="alf/widefield")
```

**Frame cache:** The raw `.mov` (JPEG2000 compressed) is decoded once into a binary
`frames.dat` memmap file using `build_frame_cache()` in `conversion/build_cache.py`.
This enables fast random-access frame reads during NWB writing without re-decoding.
The cache path is auto-derived inside `convert_raw_session()` as
`one.eid2path(eid) / "raw_widefield_data" / "wf_cache"` — no path argument is required.

**Dual-wavelength demultiplexing:** Frames alternate between two excitation wavelengths.
`WidefieldRawNWBConverter.temporally_align_data_interfaces()` reads
`imaging.imagingLightSource.npy` to assign each frame to the correct wavelength before writing.
See [temporal_alignment.md](temporal_alignment.md) for details.

**NWB output** (in `nwbfile.acquisition`):

| NWB object | Type | Excitation | Description |
|---|---|---|---|
| `OnePhotonSeriesCalcium` | `OnePhotonSeries` | 470 nm (blue) | GCaMP calcium signal |
| `OnePhotonSeriesIsosbestic` | `OnePhotonSeries` | 405 nm (violet) | Isosbestic control |

Both series:
- Shape: `(n_frames, height, width)` — stored time-first
- Timestamps: per-frame, in seconds, on the NIDQ clock
- Linked to their respective `ImagingPlane` and `Device` objects

**Device and imaging plane metadata** (`_metadata/widefield_ophys_metadata.yaml`):

| Object | Name | Excitation λ | Emission λ | Indicator |
|---|---|---|---|---|
| `Device` | `WidefieldMicroscope` | — | — | — |
| `ImagingPlane` | `ImagingPlaneCalcium` | 470 nm | 510 nm | GCaMP6f |
| `ImagingPlane` | `ImagingPlaneIsosbestic` | 405 nm | 510 nm | GCaMP6f |

---

## 2. Synchronization

The pipeline selects one sync interface per session based on file availability.
`IblNIDQInterface` (NIDQ board) is preferred; `IblWidefieldDAQInterface` (widefield DAQ board)
is used as a fallback. Both produce the same NWB object types (see comparison below).

### 2a. NIDQ Interface (preferred)

**Interface:** `IblNIDQInterface`

**Source files** (`raw_ephys_data/`):

| ONE file | Description |
|---|---|
| `_spikeglx_ephysData_g0_t0.nidq.cbin` | Compressed NIDQ recording (analog channels) |
| `_spikeglx_ephysData_g0_t0.nidq.meta` | SpikeGLX metadata (sample rate, channel config) |
| `_spikeglx_ephysData_g0_t0.nidq.ch` | Compression metadata |
| `_spikeglx_ephysData_g0_t0.nidq.wiring.json` | Port-to-device wiring map |

**ONE API access:**

```python
one.load_dataset(eid, "_spikeglx_ephysData_g0_t0.nidq.cbin", collection="raw_ephys_data", download_only=True)
one.load_dataset(eid, "_spikeglx_ephysData_g0_t0.nidq.meta", collection="raw_ephys_data")
one.load_dataset(eid, "_spikeglx_ephysData_g0_t0.nidq.ch", collection="raw_ephys_data")
one.load_dataset(eid, "_spikeglx_ephysData_g0_t0.nidq.wiring.json", collection="raw_ephys_data")
```

**Wiring.json structure:**

```json
{
  "SYNC_WIRING_DIGITAL": {
    "P0.0": "left_camera",
    "P0.1": "right_camera",
    "P0.2": "body_camera",
    "P0.3": "imec_sync",
    "P0.4": "frame2ttl",
    "P0.5": "rotary_encoder_0",
    "P0.6": "rotary_encoder_1",
    "P0.7": "audio"
  },
  "SYNC_WIRING_ANALOG": {
    "AI0": "bpod"
  }
}
```

Only devices present in `wiring.json` are included in the NWB file.

**NWB output — Digital channels** (in `nwbfile.acquisition`):

| Device | NWB name | Label 0 | Label 1 |
|---|---|---|---|
| `left_camera` | `EventsLeftCamera` | `exposure_end` | `frame_start` |
| `right_camera` | `EventsRightCamera` | `exposure_end` | `frame_start` |
| `body_camera` | `EventsBodyCamera` | `exposure_end` | `frame_start` |
| `imec_sync` | `EventsImecSync` | `sync_low` | `sync_high` |
| `frame2ttl` | `EventsFrame2ttl` | `screen_dark` | `screen_bright` |
| `rotary_encoder_0` | `EventsRotaryEncoder0` | `phase_low` | `phase_high` |
| `rotary_encoder_1` | `EventsRotaryEncoder1` | `phase_low` | `phase_high` |
| `audio` | `EventsAudio` | `audio_off` | `audio_on` |

Each `LabeledEvents` object contains:
- `timestamps`: event times in seconds (NIDQ clock)
- `data`: integer array (0 or 1) corresponding to the label list
- `labels`: `["label_for_0", "label_for_1"]`

**NWB output — Analog channels** (in `nwbfile.acquisition`):

| Device | NWB name | Description |
|---|---|---|
| `bpod` | `TimeSeriesBpod` | Analog voltage from the Bpod behavioral control system |

Each `TimeSeries` contains:
- `data`: voltage values (float, volts)
- `rate`: NIDQ sample rate from `.meta` (typically 30,000 Hz)
- `starting_time`: `0.0` (NIDQ clock starts at t=0 when recording begins)
- `unit`: `"volts"`

---

### 2b. Widefield DAQ Interface (fallback)

**Interface:** `IblWidefieldDAQInterface`

Used when `raw_ephys_data/` is absent and `raw_sync_data/` is available instead.

**Source files** (`raw_sync_data/`):

| ONE file | Description |
|---|---|
| `_spikeglx_DAQdata.wiring.json` | Port-to-device wiring map |
| `_spikeglx_DAQdata.raw.cbin` | Compressed DAQ recording (analog channels) |
| `_spikeglx_DAQdata.raw.meta` | SpikeGLX metadata (sample rate, sync channel config) |
| `_spikeglx_DAQdata.raw.ch` | Compression metadata |
| `_spikeglx_sync.channels.npy` | Pre-extracted: channel index per event |
| `_spikeglx_sync.polarities.npy` | Pre-extracted: polarity (±1) per event |
| `_spikeglx_sync.times.npy` | Pre-extracted: timestamp (s) per event |

**ONE API access:**

```python
one.load_dataset(eid, "_spikeglx_DAQdata.wiring.json", collection="raw_sync_data")
one.load_dataset(eid, "_spikeglx_DAQdata.raw.cbin", collection="raw_sync_data", download_only=True)
one.load_dataset(eid, "_spikeglx_DAQdata.raw.meta", collection="raw_sync_data")
one.load_dataset(eid, "_spikeglx_DAQdata.raw.ch", collection="raw_sync_data")
one.load_object(eid, "_spikeglx_sync", collection="raw_sync_data")
```

**Wiring.json structure:**

```json
{
  "SYSTEM": "Widefield",
  "SYNC_WIRING_DIGITAL": {
    "P0.0": "left_camera",
    "P0.1": "right_camera",
    "P0.2": "body_camera",
    "P0.3": "frame_trigger",
    "P0.4": "frame2ttl",
    "P0.5": "rotary_encoder_0",
    "P0.6": "rotary_encoder_1",
    "P0.7": "audio"
  },
  "SYNC_WIRING_ANALOG": {
    "AI0": "bpod",
    "AI1": "laser",
    "AI2": "laser_ttl"
  }
}
```

**Digital channel loading:** Events are read from the pre-extracted
`_spikeglx_sync.{channels,polarities,times}.npy` files. The channel index for each device
comes from its `P0.x` port in `wiring.json`.

**NWB output — Digital channels** (in `nwbfile.acquisition`):

| Device | NWB name | Label 0 | Label 1 |
|---|---|---|---|
| `left_camera` | `EventsLeftCamera` | `exposure_end` | `frame_start` |
| `right_camera` | `EventsRightCamera` | `exposure_end` | `frame_start` |
| `body_camera` | `EventsBodyCamera` | `exposure_end` | `frame_start` |
| `frame_trigger` | `EventsFrameTrigger` | `frame_off` | `frame_on` |
| `frame2ttl` | `EventsFrame2ttl` | `screen_dark` | `screen_bright` |
| `rotary_encoder_0` | `EventsRotaryEncoder0` | `phase_low` | `phase_high` |
| `rotary_encoder_1` | `EventsRotaryEncoder1` | `phase_low` | `phase_high` |
| `audio` | `EventsAudio` | `audio_off` | `audio_on` |
| `bpod` | `EventsBpodDigital` | `ttl_low` | `ttl_high` |

**NWB output — Analog channels** (in `nwbfile.acquisition`):

| Device | NWB name | Description |
|---|---|---|
| `bpod` | `TimeSeriesBpod` | Analog voltage from Bpod behavioral control system |
| `laser` | `TimeSeriesLaser` | Laser power output (optogenetic stimulation) |
| `laser_ttl` | `TimeSeriesLaserTTL` | Laser activation TTL voltage |

Each `TimeSeries` contains:
- `data`: voltage values (float, volts) from the `.cbin` file
- `rate`: DAQ sample rate from `.meta`
- `starting_time`: For devices also present as digital channels (e.g., `bpod`), the timestamp
  of the first digital event on that device's port is used as `starting_time`. For devices with
  no digital counterpart, the timestamp of the first event on the SpikeGLX sync channel is used
  as a fallback; if the sync channel is absent from the `.meta` file, `starting_time` defaults to `0.0`.
- `unit`: `"volts"`

### NIDQ vs DAQ: NWB output comparison

| NWB object | NIDQ | DAQ | Notes |
|---|---|---|---|
| `EventsLeftCamera` | ✓ | ✓ | |
| `EventsRightCamera` | ✓ | ✓ | |
| `EventsBodyCamera` | ✓ | ✓ | |
| `EventsImecSync` | ✓ | | NIDQ only |
| `EventsFrameTrigger` | | ✓ | DAQ only — widefield frame sync |
| `EventsBpodDigital` | | ✓ | DAQ only — digital TTL from Bpod |
| `EventsFrame2ttl` | ✓ | ✓ | |
| `EventsRotaryEncoder0/1` | ✓ | ✓ | |
| `EventsAudio` | ✓ | ✓ | |
| `TimeSeriesBpod` | ✓ | ✓ | |
| `TimeSeriesLaser` | | ✓ | DAQ only |
| `TimeSeriesLaserTTL` | | ✓ | DAQ only |

---

## 3. Raw Behavior Videos

**Interface:** `RawVideoInterface` (from `ibl_to_nwb`; one instance per camera)

**Source files** (`raw_video_data/`):

| ONE file | Camera |
|---|---|
| `_iblrig_leftCamera.raw.mp4` | Left side camera |
| `_iblrig_rightCamera.raw.mp4` | Right side camera |
| `_iblrig_bodyCamera.raw.mp4` | Body/ventral camera |

Files are linked externally — the `.mp4` is not embedded in the NWB file.
Only cameras with data available on Alyx are included.

**ONE API access:**

```python
one.list_datasets(eid, filename="*Camera.raw.mp4*")
one.load_dataset(eid, "_iblrig_leftCamera.raw.mp4", collection="raw_video_data", download_only=True)
```

**NWB output** (in `nwbfile.acquisition`):

| NWB object | Type | Description |
|---|---|---|
| `ImageSeriesLeftCamera` | `ImageSeries` | Left camera video (external `.mp4` link) |
| `ImageSeriesRightCamera` | `ImageSeries` | Right camera video (external `.mp4` link) |
| `ImageSeriesBodyCamera` | `ImageSeries` | Body camera video (external `.mp4` link) |

---

## 4. Session Epochs

**Interface:** `SessionEpochsInterface` (from `ibl_to_nwb`)

Defines the high-level temporal structure of the session (e.g., active task vs. passive replay).

**Source file:**

| ONE file | Collection | Description |
|---|---|---|
| `_ibl_passivePeriods.intervalsTable.csv` | `alf` | Passive and task phase intervals |

**ONE API access:**

```python
one.load_dataset(eid, "_ibl_passivePeriods.intervalsTable", collection="alf")
```

**NWB output** (in `nwbfile.epochs`):

| NWB object | Type | Columns |
|---|---|---|
| `epochs` | `TimeIntervals` | `start_time`, `stop_time`, `protocol_type`, `protocol_name` |

---

## 5. Anatomical Landmarks and Atlas Registration

**Interface:** `IblWidefieldLandmarksInterface`

Included when `widefieldLandmarks.dorsalCortex.json` is available for the session.

**Source file:**

| ONE file | Collection | Description |
|---|---|---|
| `widefieldLandmarks.dorsalCortex.json` | `alf/widefield` | Manually identified landmarks + affine transform to Allen CCF |

**ONE API access:**

```python
one.load_dataset(eid, "widefieldLandmarks.dorsalCortex", collection="alf/widefield")
```

The JSON contains: manually identified landmark points (bregma, lambda, etc.) in pixel
coordinates, an affine transform matrix to Allen CCFv3 space, bregma offset, and per-pixel
resolution.

**NWB output** (uses `ndx_anatomical_localization` extension):

| Location | NWB name | Type | Description |
|---|---|---|---|
| `nwbfile.lab_meta_data` | `atlas_registration` | `AtlasRegistration` | Images, affine transform, and landmarks grouped together |
| — | `MeanImage` | `GrayscaleImage` | Source (camera-space) mean FOV image |
| — | `RegisteredImage` | `GrayscaleImage` | Mean FOV warped into atlas space |
| — | `AtlasProjectionImage` | `GrayscaleImage` | Allen CCF dorsal-cortex reference projection |
| — | `AffineTransformation` | `AffineTransformation` | 3×3 homogeneous affine matrix: source px → registered px |
| — | `landmarks` | `Landmarks` | Table of named anatomical landmarks (source, registered, and reference pixel coords) |
| `nwbfile.lab_meta_data` | `localization` | `Localization` | Root container for coordinate spaces and dense coordinate maps |
| — | `IBLBregmaProjection` | `Space` | IBL bregma coordinate frame (RAS: x=ML, y=AP, z=DV; units: µm) |
| — | `AllenCCFv3Space` | `AllenCCFv3Space` | Allen CCFv3 reference frame (PIR+ orientation; units: µm) |
| `Localization` | `AnatomicalCoordinatesImageIBLBregma` | `AnatomicalCoordinatesImage` | Per-pixel (x=ML, y=AP, z=DV) in IBL bregma space + Allen region acronym for every pixel of the registered image |
| `Localization` | `AnatomicalCoordinatesImageCCFv3` | `AnatomicalCoordinatesImage` | Per-pixel (x=AP, y=DV, z=ML) in Allen CCFv3 space + Allen region acronym for every pixel of the registered image |
| `Localization` | `RegisteredImageBrainRegionMasksIBLBregma` | `BrainRegionMasks` | Sparse table of (x, y, brain_region_id) for every in-atlas pixel of the registered image |
| `Localization` | `SourceImageBrainRegionMasksIBLBregma` | `BrainRegionMasks` | Same masks warped back to source (camera) image space via inverse affine |
| `Localization` | `AnatomicalCoordinatesIBLBregma` | `AnatomicalCoordinatesTable` | Landmark coordinates in IBL bregma space (µm) |
| `Localization` | `AnatomicalCoordinatesCCFv3` | `AnatomicalCoordinatesTable` | Landmark coordinates in Allen CCFv3 space (µm) |

`AnatomicalCoordinatesImageIBLBregma` and `AnatomicalCoordinatesImageCCFv3` are linked to
`OnePhotonSeriesCalcium` via their `localized_entity` field when the raw pipeline is used.
Out-of-atlas pixels carry the string `"out-of-atlas"` in the `brain_region` array.
