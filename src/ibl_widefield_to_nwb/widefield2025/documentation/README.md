# IBL Widefield-to-NWB: Conversion Documentation

This folder documents how IBL widefield session data is loaded from the ONE API and written
to NWB format. It is intended as a reference for IBL collaborators reviewing the conversion.

## Documents

| File | Contents |
|---|---|
| [README.md](README.md) | This file — overview, session structure, pipeline comparison |
| [temporal_alignment.md](temporal_alignment.md) | Synchronization architecture and empirical validation |
| [raw_nwb.md](raw_nwb.md) | Raw NWB file: widefield frames, DAQ/NIDQ sync, behavior videos |
| [processed_nwb.md](processed_nwb.md) | Processed NWB file: SVD components, landmarks, behavior |
| [consistency_checks.md](consistency_checks.md) | Post-conversion consistency checks: usage, check catalogue, how to add new checks |
| [open_questions.md](open_questions.md) | Open questions for IBL |

---

## Overview

Each session produces two NWB files:

| File | Entry point | Contents |
|---|---|---|
| `sub-{subject}_ses-{eid}_desc-raw_behavior+ophys.nwb` | `conversion/raw.py` | Full-resolution widefield frames, sync signals, raw behavior videos |
| `sub-{subject}_ses-{eid}_desc-processed_behavior+ophys.nwb` | `conversion/processed.py` | SVD-decomposed imaging, anatomical landmarks, processed behavior |

Both files are published on [DANDI](https://dandiarchive.org) under a session-specific folder:
`sub-{subject}/sub-{subject}_ses-{eid}_desc-{raw|processed}_behavior+ophys.nwb`

---

## ONE API Access

```python
from one.api import ONE

# public database
one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international")
eid = "d34a502f-bd06-471f-8334-df41f785e1d9"  # example session
```

**Revision pinning:** Processed behavioral data (`alf/` collection) is loaded at revision
`2025-05-06` (Brain-Wide Map standard) for reproducibility. Widefield-specific data
(`alf/widefield/`) does not yet use revision pinning.

---

## Session Directory Structure

```
<session_root>/
├── alf/
│   ├── widefield/                              # Widefield-specific processed data
│   │   ├── imaging.times.npy                  # Aligned frame timestamps (NIDQ clock)
│   │   ├── imaging.imagingLightSource.npy      # Per-frame wavelength index
│   │   ├── imagingLightSource.properties.htsv # Wavelength → LED mapping
│   │   ├── widefieldU.images.npy               # SVD spatial components (U)
│   │   ├── widefieldSVT.uncorrected.npy        # SVD temporal traces, uncorrected
│   │   ├── widefieldSVT.haemoCorrected.npy     # SVD temporal traces, haemo-corrected
│   │   ├── widefieldChannels.frameAverage.npy  # Mean frame per wavelength
│   │   └── widefieldLandmarks.dorsalCortex.json# Anatomical landmarks + CCF affine transform
│   │
│   ├── _ibl_trials.*.npy                       # Trial events (many attributes)
│   ├── wheel.timestamps.npy                    # Wheel sample timestamps
│   ├── wheel.position.npy                      # Wheel angular position (rad)
│   ├── wheelMoves.intervals.npy                # Movement bout intervals
│   ├── wheelMoves.peakAmplitude.npy            # Movement amplitudes
│   ├── licks.times.npy                         # Lick event timestamps
│   ├── _ibl_{camera}Camera.times.npy           # Camera frame timestamps (one per camera)
│   ├── _ibl_{camera}Camera.features.pqt        # Pupil diameter estimates
│   ├── _ibl_{camera}Camera.lightningPose.pqt   # LightningPose keypoint tracks (preferred)
│   ├── _ibl_{camera}Camera.dlc.pqt             # DeepLabCut keypoint tracks (fallback)
│   ├── {camera}Camera.ROIMotionEnergy.npy      # Frame-level motion energy per camera
│   ├── {view}ROIMotionEnergy.position.npy      # ROI position [x, y, w, h] in pixels
│   ├── _ibl_passivePeriods.intervalsTable.csv  # Passive session phase intervals
│   ├── _ibl_passiveStims.table.csv             # Passive replay stimulus events
│   ├── _ibl_passiveGabor.table.csv             # Gabor patch parameters
│   └── _ibl_passiveRFM.times.npy              # Receptive field mapping stim times
│
├── raw_widefield_data/
│   ├── imaging.frames.mov                      # Raw video: all wavelengths interleaved
│   ├── widefieldChannels.wiring.htsv           # Channel gain, exposure, wavelength
│   └── widefieldEvents.raw.camlog             # Camera hardware event log
│
├── raw_ephys_data/                             # NIDQ sync (preferred)
│   ├── _spikeglx_ephysData_g0_t0.nidq.cbin   # Compressed NIDQ recording
│   ├── _spikeglx_ephysData_g0_t0.nidq.meta   # SpikeGLX metadata
│   ├── _spikeglx_ephysData_g0_t0.nidq.ch     # Compression metadata
│   └── _spikeglx_ephysData_g0_t0.nidq.wiring.json  # Port-to-device wiring map
│
├── raw_sync_data/                              # Widefield DAQ (fallback when NIDQ absent)
│   ├── _spikeglx_DAQdata.wiring.json          # Port-to-device wiring map
│   ├── _spikeglx_DAQdata.raw.cbin             # Compressed DAQ recording (analog channels)
│   ├── _spikeglx_DAQdata.raw.meta             # SpikeGLX metadata (sync channel info)
│   ├── _spikeglx_DAQdata.raw.ch               # Compression metadata
│   ├── _spikeglx_sync.channels.npy            # Pre-extracted: channel index per event
│   ├── _spikeglx_sync.polarities.npy          # Pre-extracted: polarity (±1) per event
│   └── _spikeglx_sync.times.npy              # Pre-extracted: timestamp (s) per event
│
├── raw_video_data/
│   ├── _iblrig_leftCamera.raw.mp4             # Left camera video
│   ├── _iblrig_rightCamera.raw.mp4            # Right camera video
│   └── _iblrig_bodyCamera.raw.mp4            # Body camera video
│
└── raw_passive_data/
    └── _iblrig_RFMapStim.raw.bin              # Receptive field mapping stimulus binary
```

---

## Pipeline Comparison

| Data stream | Raw NWB | Processed NWB | NWB type |
|---|---|---|---|
| **Widefield imaging** | | | |
| Raw frames (interleaved) | ✓ | | `OnePhotonSeries` (acquisition) |
| SVD spatial components (U) | | ✓ | `PlaneSegmentation` (processing/ophys) |
| SVD temporal traces (SVT) | | ✓ | `RoiResponseSeries` (processing/ophys) |
| Mean images per wavelength | | ✓ | `GrayscaleImage` in `Images` (processing/ophys) |
| Anatomical landmarks + CCF transform | ✓ | ✓ | `Landmarks`, `AtlasRegistration` (lab_meta_data) |
| Per-pixel atlas coordinates (IBL bregma + CCFv3) | ✓ | ✓ | `AnatomicalCoordinatesImage` ×2 (lab_meta_data/Localization) |
| Brain region masks (registered + source space) | ✓ | ✓ | `BrainRegionMasks` ×2 (lab_meta_data/Localization) |
| **Synchronization** | | | |
| NIDQ digital channels | ✓ | | `LabeledEvents` (acquisition) |
| NIDQ analog channels | ✓ | | `TimeSeries` (acquisition) |
| Widefield DAQ digital channels | ✓ | | `LabeledEvents` (acquisition) |
| Widefield DAQ analog channels | ✓ | | `TimeSeries` (acquisition) |
| **Behavior** | | | |
| Raw camera videos | ✓ | | `ImageSeries` (acquisition) |
| Session epochs (task / passive) | ✓ | ✓ | `TimeIntervals` (nwbfile.epochs) |
| Trials | | ✓ | `TimeIntervals` (nwbfile.trials) |
| Wheel position / velocity | | ✓ | `SpatialSeries`, `TimeSeries` (processing/wheel) |
| Wheel movement intervals | | ✓ | `TimeIntervals` (processing/wheel) |
| Lick events | | ✓ | `Events` (processing/lick_times) |
| Pupil diameter | | ✓ | `TimeSeries` (processing/pupil) |
| ROI motion energy | | ✓ | `TimeSeries` (processing/motion_energy) |
| Pose estimation (LP / DLC) | | ✓ | `PoseEstimation` (processing/pose_estimation) |
| Passive intervals | | ✓ | `TimeIntervals` (processing/passive) |
| Passive replay stimuli | | ✓ | `TimeIntervals` (processing/passive) |
| Gabor patch presentations | | ✓ | `TimeIntervals` (processing/passive) |
| RFM stimulus | | ✓ | `TimeSeries` (processing/passive) |

---

## NWB Extensions

| Extension | Used for |
|---|---|
| `ndx_events` | `LabeledEvents` (sync channels); `Events` (lick times) |
| `ndx_pose` | `PoseEstimation` / `PoseEstimationSeries` for LightningPose / DLC |
| `ndx_ibl` | `IblSubject`, `IblMetadata` for IBL-specific session metadata |
| `ndx_anatomical_localization` | `Localization`, `AtlasRegistration`, `Landmarks`, `AffineTransformation`, `AnatomicalCoordinatesImage` (IBL bregma + CCFv3), `BrainRegionMasks` (registered + source), `AnatomicalCoordinatesTable` (IBL bregma + CCFv3) — enabled in both raw and processed pipelines |

---

## Metadata Sources

| Source | Contents |
|---|---|
| `_metadata/widefield_general_metadata.yaml` | Session description, keywords, experimenter, species, strain |
| `_metadata/widefield_ophys_metadata.yaml` | `Device`, `ImagingPlane`, `OnePhotonSeries`, SVD component descriptions |
| `_metadata/widefield_DAQ_metadata.yaml` | `TimeSeries` and `LabeledEvents` names/descriptions for DAQ channels |
| `_metadata/widefield_nidq_metadata.yaml` | `TimeSeries` and `LabeledEvents` names/descriptions for NIDQ channels |
| IBL ONE API (Alyx) | Session date, lab, institution, task protocol, subject weight/age/sex/genotype |
