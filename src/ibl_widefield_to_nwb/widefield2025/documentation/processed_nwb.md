# Processed NWB File

**Entry point:** `convert_processed_session()` in `conversion/processed.py`

**Converter:** `WidefieldProcessedNWBConverter`

**Output filename:** `sub-{subject}_ses-{eid}_desc-processed_behavior+ophys.nwb`

The processed NWB file contains SVD-decomposed imaging data, anatomical landmark registration,
and all processed behavioral data available for the session.

---

## Data Flow

```
SOURCE DATA                           INTERFACE                         NWB CONTAINER

OPTICAL PHYSIOLOGY
──────────────────
alf/widefield/
├── widefieldU.images.npy      ──→  WidefieldSVDInterface (×2)  ──→  SVDSpatialComponents
├── widefieldSVT.uncorrected.npy    (one per wavelength)               (ImageSegmentation)
├── widefieldSVT.haemoCorrected.npy                                    SVDTemporalComponentsCalcium
├── widefieldChannels.                                                  SVDTemporalComponentsIsosbestic
│   frameAverage.npy                                                    (PlaneSegmentation)
└── imaging.*.npy                                                       RoiResponseSeries (×3)
                                                                        SummaryImages (GrayscaleImage)
                                                                        (processing/ophys)

alf/widefield/
└── widefieldLandmarks.        ──→  IblWidefieldLandmarksInterface ──→  Localization
    dorsalCortex.json                                                   Landmarks, AtlasRegistration
                                                                        AnatomicalCoordinatesTable*
                                                                        (lab_meta_data)

BEHAVIORAL TASKS
────────────────
alf/
├── _ibl_trials.*.npy          ──→  BrainwideMapTrialsInterface  ──→  trials (TimeIntervals)
                                                                        (nwbfile.trials)

alf/
├── wheel.timestamps.npy       ──→  WheelPositionInterface       ──→  WheelPosition (SpatialSeries)
├── wheel.position.npy              WheelKinematicsInterface           WheelPositionSmoothed
├── wheelMoves.intervals.npy        WheelMovementsInterface            WheelVelocitySmoothed
└── wheelMoves.peakAmplitude.npy                                        WheelMovementIntervals
                                                                        (processing/wheel)

alf/
└── licks.times.npy            ──→  LickInterface                ──→  EventsLickTimes (Events)
                                                                        (processing/lick_times)

CAMERA-BASED PROCESSING
───────────────────────
alf/
├── _ibl_*Camera.features.pqt  ──→  PupilTrackingInterface       ──→  {Left|Right}PupilDiameter
└── _ibl_*Camera.times.npy          (per available camera)             {Left|Right}PupilDiameterSmoothed
                                                                        (flat TimeSeries)
                                                                        (processing/pupil)

alf/
├── *Camera.ROIMotionEnergy.npy──→  RoiMotionEnergyInterface      ──→  {Left|Right|Body}Camera
└── *Camera.times.npy               (per available camera)             MotionEnergy (TimeSeries)
                                                                        (processing/motion_energy)

alf/
├── _ibl_*Camera.lightningPose ──→  IblPoseEstimationInterface   ──→  {Left|Right|Body}Camera
│   .pqt  (preferred)               (per available camera)             (PoseEstimation)
├── _ibl_*Camera.dlc.pqt                                                Skeletons (Skeletons)
└── _ibl_*Camera.times.npy                                              (processing/pose_estimation)

PASSIVE PERIOD
──────────────
alf/
├── _ibl_passivePeriods.       ──→  SessionEpochsInterface       ──→  epochs (TimeIntervals)
│   intervalsTable.csv                                                  (nwbfile.epochs)
├── _ibl_passiveStims.         ──→  PassiveReplayStimInterface   ──→  passive_task_replay
│   table.csv                                                           (TimeIntervals)
├── _ibl_passiveGabor.         ──→  (included in above)          ──→  gabor_table (TimeIntervals)
│   table.csv
└── _ibl_passiveRFM.times.npy  ──→  PassiveRFMInterface          ──→  rfm_stim (TimeSeries)
    + raw_passive_data/                                                 (processing/passive)
        _iblrig_RFMapStim.raw.bin
```

---

## 1. Widefield SVD Components

**Interface:** `WidefieldSVDInterface` (one instance per excitation wavelength)

**Source files** (from `alf/widefield/`):

| ONE file | Shape | Description |
|---|---|---|
| `widefieldU.images.npy` | `(height, width, n_components)` | SVD spatial components (U matrix) |
| `widefieldSVT.uncorrected.npy` | `(n_components, n_total_frames)` | Temporal components, uncorrected |
| `widefieldSVT.haemoCorrected.npy` | `(n_components, n_470nm_frames)` | Temporal components, haemo-corrected (470 nm only) |
| `widefieldChannels.frameAverage.npy` | `(n_wavelengths, height, width)` | Mean frame per wavelength |
| `imaging.times.npy` | `(n_total_frames,)` | Aligned frame timestamps |
| `imaging.imagingLightSource.npy` | `(n_total_frames,)` | Per-frame wavelength index |
| `imagingLightSource.properties.htsv` | — | Wavelength → LED property mapping |

**ONE API access:**

```python
one.load_object(eid, "widefieldU", collection="alf/widefield")
one.load_object(eid, "widefieldSVT", collection="alf/widefield")
one.load_object(eid, "widefieldChannels", collection="alf/widefield")
one.load_object(eid, "imaging", collection="alf/widefield")
one.load_dataset(eid, "imagingLightSource.properties", collection="alf/widefield")
```

**NWB output** (all under `nwbfile.processing["ophys"]`):

Two parallel `PlaneSegmentation` objects are created — one per wavelength — each containing
the SVD spatial components (U matrix) as ROI image masks, linked to their `ImagingPlane`.

| NWB location | Name | Type | Description |
|---|---|---|---|
| `processing["ophys"]` | `SVDSpatialComponents` | `ImageSegmentation` | Container for both plane segmentations |
| — | `SVDTemporalComponentsCalcium` | `PlaneSegmentation` | Spatial components for 470 nm; each ROI = one U column |
| — | `SVDTemporalComponentsIsosbestic` | `PlaneSegmentation` | Spatial components for 405 nm |
| `processing["ophys"]` | `SVDTemporalComponents` | `Fluorescence` | Container for temporal traces |
| — | `DenoisedSVDTemporalComponentsCalcium` | `RoiResponseSeries` | Uncorrected SVT traces, 470 nm |
| — | `HaemoCorrectedSVDTemporalComponentsCalcium` | `RoiResponseSeries` | Haemo-corrected SVT traces, 470 nm |
| — | `DenoisedSVDTemporalComponentsIsosbestic` | `RoiResponseSeries` | Uncorrected SVT traces, 405 nm |
| `processing["ophys"]` | `SummaryImages` | `Images` | Mean frames per wavelength |
| — | `MeanImage` | `GrayscaleImage` | Mean frame under 470 nm excitation |
| — | `MeanImageIsosbestic` | `GrayscaleImage` | Mean frame under 405 nm excitation |

**Reconstructing full-frame ΔF/F:**

```python
import numpy as np
import wfield

# Spatial components (U):
# plane_segmentation["image_mask"].data has shape: (n_components, height, width)
U = nwbfile.processing["ophys"]["SVDSpatialComponents"]["SVDTemporalComponentsCalcium"].image_mask[:]
print(f"Spatial components U shape (n_components, height, width): {U.shape}")

# Haemocorrected temporal components (SVT):
# roi_response_dff.data has shape: (time, n_components)
SVT = nwbfile.processing["ophys"]["SVDTemporalComponents"]["DenoisedSVDTemporalComponentsCalcium"].data[:]
print(f"Temporal components SVT shape (time, n_components): {SVT.shape}")

# --- Prepare shapes for SVDStack ---

# wfield.SVDStack expects:
#   U_stack:  (height, width, n_components)
#   SVT_stack: (n_components, time)
U_stack = np.transpose(U, (1, 2, 0))                  # (height, width, n_components)
SVT_stack = SVT.T                                     # (n_components, time)

print(f"U_stack shape (height, width, n_components): {U_stack.shape}")
print(f"SVT_stack shape (n_components, time):         {SVT_stack.shape}")

# --- Build the reconstructed imaging stack ---
# Resulting stack has shape: (time, height, width)
stack = wfield.SVDStack(U_stack, SVT_stack)
print(f"Reconstructed stack shape (time, height, width): {stack.shape}")

```

---

## 2. Anatomical Landmarks and Atlas Registration

**Interface:** `IblWidefieldLandmarksInterface`

> **Status: Enabled.** The landmarks interface is active in both the raw and processed pipelines.
> It is included whenever `widefieldLandmarks.dorsalCortex.json` is available for a session.
> An `AnatomicalCoordinatesImage` providing per-pixel atlas coordinates in source image space
> (linked to the mean image / `OnePhotonSeries`) is under development.

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
| `nwbfile.lab_meta_data` | `Localization` | `Localization` | Root container for spatial registration |
| — | `IBLBregmaProjection` | `Space` | IBL bregma coordinate frame (RAS: x=ML, y=AP, z=DV; units: µm) |
| — | `AllenCCFv3Space` | `Space` | Allen CCFv3 reference frame (PIR+ orientation) |
| `processing["ophys"]` | `RegisteredImages` | `Images` | Widefield FOV images in registered space |
| — | `RegisteredImage` | `GrayscaleImage` | Post-registration mean FOV image |
| — | `AtlasProjectionImage` | `GrayscaleImage` | Allen CCF dorsal cortex atlas projection |
| `Localization` | `landmarks` | `Landmarks` | Table of named anatomical landmarks |
| `Localization` | `affine_transformation` | `AffineTransformation` | 3×3 affine matrix from image space to atlas space |
| `Localization` | `AtlasRegistration` | `AtlasRegistration` | Links images, landmarks, and transformation |
| `Localization` | `AnatomicalCoordinatesIBLBregma` | `AnatomicalCoordinatesTable` | Landmark coordinates in IBL bregma space (µm) |
| `Localization` | `AnatomicalCoordinatesCCFv3` | `AnatomicalCoordinatesTable` | Landmark coordinates in Allen CCFv3 space |
| `Localization` | `RegisteredImageAnatomicalCoordinatesIBLBregma` | `AnatomicalCoordinatesImage` | Per-pixel (x, y, z) in IBL bregma space + Allen region ID/acronym |

---

## 3. Trials

**Interface:** `BrainwideMapTrialsInterface` (from `ibl_to_nwb`)

**Source data:** Loaded via `brainbox.io.one.SessionLoader.load_trials()` at revision `2025-05-06`.

| ONE ALF object | Collection | Description |
|---|---|---|
| `_ibl_trials.*` | `alf` | Trial events, choices, contrasts, outcomes |

**ONE API access:**

```python
one.load_object(eid, "trials", collection="alf")
```

Key datasets: `_ibl_trials.intervals.npy`, `_ibl_trials.choice.npy`, `_ibl_trials.feedbackType.npy`,
`_ibl_trials.rewardVolume.npy`, `_ibl_trials.contrastLeft.npy`, `_ibl_trials.contrastRight.npy`,
`_ibl_trials.probabilityLeft.npy`, `_ibl_trials.feedback_times.npy`, `_ibl_trials.response_times.npy`,
`_ibl_trials.stimOff_times.npy`, `_ibl_trials.stimOn_times.npy`, `_ibl_trials.goCue_times.npy`,
`_ibl_trials.firstMovement_times.npy`

**NWB output** (in `nwbfile.trials`):

| NWB object | Type | Columns |
|---|---|---|
| `trials` | `TimeIntervals` | `start_time`, `stop_time`, `quiescence_period`, `gabor_stimulus_onset_time`, `gabor_stimulus_offset_time`, `auditory_cue_time`, `wheel_movement_onset_time`, `choice_registration_time`, `feedback_time`, `gabor_stimulus_contrast`, `gabor_stimulus_side`, `mouse_wheel_choice`, `is_mouse_rewarded`, `reward_volume_uL`, `probability_left`, `block_type`, `block_index` |

---

## 4. Wheel

**Interfaces:** `WheelPositionInterface`, `WheelKinematicsInterface`, `WheelMovementsInterface`
(all from `ibl_to_nwb`)

**Source data** (revision `2025-05-06`):

| ONE file | Collection | Description |
|---|---|---|
| `wheel.timestamps.npy` | `alf` | Sample timestamps |
| `wheel.position.npy` | `alf` | Angular position (radians) |
| `wheelMoves.intervals.npy` | `alf` | Movement bout start/stop times |
| `wheelMoves.peakAmplitude.npy` | `alf` | Peak displacement per movement bout |

**ONE API access:**

```python
one.load_object(eid, "wheel", collection="alf")
one.load_object(eid, "wheelMoves", collection="alf")
```

**NWB output** (in `nwbfile.processing["wheel"]`):

| NWB object | Type | Unit | Sampling |
|---|---|---|---|
| `WheelPosition` | `SpatialSeries` (in `CompassDirection`) | `rad` | Irregular timestamps |
| `WheelPositionSmoothed` | `SpatialSeries` | `rad` | 1000 Hz (`rate` + `starting_time`) |
| `WheelVelocitySmoothed` | `TimeSeries` | `rad/s` | 1000 Hz (`rate` + `starting_time`) |
| `WheelAccelerationSmoothed` | `TimeSeries` | `rad/s²` | 1000 Hz (`rate` + `starting_time`) |
| `WheelMovementIntervals` | `TimeIntervals` | — | One row per movement bout |

`WheelMovementIntervals` columns: `start_time`, `stop_time`, `peak_amplitude`

> **Access note:** `WheelPositionSmoothed`, `WheelVelocitySmoothed`, and
> `WheelAccelerationSmoothed` use `rate` and `starting_time` rather than `timestamps`.
> Reconstruct time as:
> ```python
> t = series.starting_time + np.arange(len(series.data)) / series.rate
> ```

---

## 5. Lick Times

**Interface:** `LickInterface` (from `ibl_to_nwb`)

**Source data** (revision `2025-05-06`):

| ONE file | Collection | Description |
|---|---|---|
| `licks.times.npy` | `alf` | Timestamps of lick events detected from DLC tongue traces |

**ONE API access:**

```python
one.load_dataset(eid, "licks.times", collection="alf", revision="2025-05-06")
```

**Availability check:**

```python
one.list_datasets(eid=eid, collection="alf", filename="licks*")
```

**NWB output** (in `nwbfile.processing["lick_times"]`):

| NWB object | Type | Description |
|---|---|---|
| `EventsLickTimes` | `Events` (ndx_events) | Timestamps of detected lick events |

---

## 6. Pupil Tracking

**Interface:** `PupilTrackingInterface` (from `ibl_to_nwb`; one per camera)

**Source data** (revision `2025-05-06`):

| ONE file | Collection | Description |
|---|---|---|
| `_ibl_{camera}Camera.features.pqt` | `alf` | Pupil diameter estimates (raw + smoothed) |
| `_ibl_{camera}Camera.times.npy` | `alf` | Camera frame timestamps |

Cameras: `leftCamera`, `rightCamera`, `bodyCamera`

**ONE API access:**

```python
one.list_datasets(eid=eid, filename="*features*")
one.load_object(eid, f"{camera_name}Camera", collection="alf", revision="2025-05-06")
```

**NWB output** (in `nwbfile.processing["pupil"]`):

Pupil `TimeSeries` objects are stored **flat** in the `pupil` processing module — there is no
`PupilTracking` wrapper container.

| NWB object | Type | Description |
|---|---|---|
| `LeftPupilDiameter` | `TimeSeries` | Raw pupil diameter from left camera |
| `LeftPupilDiameterSmoothed` | `TimeSeries` | Smoothed pupil diameter from left camera |
| `RightPupilDiameter` | `TimeSeries` | Raw pupil diameter from right camera (if available) |
| `RightPupilDiameterSmoothed` | `TimeSeries` | Smoothed pupil diameter from right camera (if available) |

Each `TimeSeries`:
- `data`: pupil diameter in pixels
- `timestamps`: camera frame times in seconds
- `unit`: `"px"`

---

## 7. ROI Motion Energy

**Interface:** `RoiMotionEnergyInterface` (from `ibl_to_nwb`; one per camera)

**Source data** (revision `2025-05-06`):

| ONE file | Collection | Description |
|---|---|---|
| `{camera}Camera.ROIMotionEnergy.npy` | `alf` | Frame-by-frame motion energy within a fixed ROI |
| `{view}ROIMotionEnergy.position.npy` | `alf` | ROI position `[x, y, width, height]` in pixels |
| `_ibl_{camera}Camera.times.npy` | `alf` | Camera frame timestamps |

Cameras: `leftCamera`, `rightCamera`, `bodyCamera`

**ONE API access:**

```python
one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
one.load_dataset(eid, f"{view}ROIMotionEnergy.position", collection="alf", revision="2025-05-06")
```

**NWB output** (in `nwbfile.processing["motion_energy"]`):

Only cameras with motion energy data available on Alyx are included.

| NWB object | Type | Unit |
|---|---|---|
| `LeftCameraMotionEnergy` | `TimeSeries` | `a.u.` |
| `RightCameraMotionEnergy` | `TimeSeries` | `a.u.` |
| `BodyCameraMotionEnergy` | `TimeSeries` | `a.u.` |

Each description includes the ROI position and size.

---

## 8. Pose Estimation

**Interface:** `IblPoseEstimationInterface` (from `ibl_to_nwb`; one per camera)

**Source data:** Loaded via `brainbox.io.one.SessionLoader.load_pose()` at revision `2025-05-06`.

| ONE file | Collection | Description |
|---|---|---|
| `_ibl_{camera}Camera.lightningPose.pqt` | `alf` | LightningPose keypoint tracks (preferred) |
| `_ibl_{camera}Camera.dlc.pqt` | `alf` | DeepLabCut tracks (fallback) |
| `_ibl_{camera}Camera.times.npy` | `alf` | Camera frame timestamps |

Tracker priority: LightningPose if available, else DLC. Low-confidence keypoints
(likelihood < 0.9) are set to `NaN` by `SessionLoader.load_pose()`.

**ONE API access:**

```python
one.list_datasets(eid=eid, filename="*.lightningPose*")
SessionLoader(one, eid, revision="2025-05-06").load_pose(tracker="lightningPose")
```

**NWB output** (in `nwbfile.processing["pose_estimation"]`):

Only cameras with pose data available on Alyx are included.

| NWB object | Type | Description |
|---|---|---|
| `LeftCamera` | `PoseEstimation` (ndx_pose) | Keypoint tracks from left camera |
| `RightCamera` | `PoseEstimation` (ndx_pose) | Keypoint tracks from right camera (if available) |
| `BodyCamera` | `PoseEstimation` (ndx_pose) | Keypoint tracks from body camera |
| `Skeletons` | `Skeletons` (ndx_pose) | Skeleton graph shared by all cameras |

Each `PoseEstimation` contains one `PoseEstimationSeries` per tracked body part, named
`PoseEstimationSeries{BodyPartPascalCase}` (e.g., `PoseEstimationSeriesLeftPaw`):
- `data`: `(n_frames, 2)` array of `[x, y]` coordinates in pixels
- `confidence`: per-frame likelihood from tracker
- `unit`: `"px"`

---

## 9. Passive Period Data

**Interfaces:** `PassiveIntervalsInterface`, `PassiveReplayStimInterface`, `PassiveRFMInterface`
(all from `ibl_to_nwb`; each conditional on data availability)

**Source files:**

| ONE file | Collection | Description |
|---|---|---|
| `_ibl_passivePeriods.intervalsTable.csv` | `alf` | Passive session phase intervals |
| `_ibl_passiveStims.table.csv` | `alf` | Passive task replay events (valves, tones, noise) |
| `_ibl_passiveGabor.table.csv` | `alf` | Gabor patch presentation parameters |
| `_ibl_passiveRFM.times.npy` | `alf` | Receptive field mapping stimulus times |
| `_iblrig_RFMapStim.raw.bin` | `raw_passive_data` | RFM stimulus binary data |

**ONE API access:**

```python
one.load_dataset(eid, "_ibl_passivePeriods.intervalsTable", collection="alf")
one.load_dataset(eid, "_ibl_passiveStims.table", collection="alf")
one.load_dataset(eid, "_ibl_passiveGabor.table", collection="alf")
one.load_dataset(eid, "_ibl_passiveRFM.times", collection="alf")
```

**NWB output:**

| Location | NWB name | Type | Columns |
|---|---|---|---|
| `nwbfile.epochs` | `epochs` | `TimeIntervals` | `start_time`, `stop_time`, `protocol_type`, `protocol_name` |
| `processing["passive"]` | `passive_task_replay` | `TimeIntervals` | `start_time`, `stop_time`, `stim_type` (valve/tone/noise) |
| `processing["passive"]` | `gabor_table` | `TimeIntervals` | `start_time`, `stop_time`, `position`, `contrast`, `phase` |
| `processing["passive"]` | `rfm_stim` | `TimeSeries` | Shape: `(n_frames, 15, 15)`, unit: `"px"` |
