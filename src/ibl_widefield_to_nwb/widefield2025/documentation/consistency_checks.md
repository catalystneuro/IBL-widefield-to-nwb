# Consistency Checks

After converting a session to NWB, run the consistency checks to verify that every data stream
in the NWB file matches the source data from the IBL ONE API.

---

## Location

| File | Purpose |
|---|---|
| `widefield2025/testing/_consistency_checks.py` | Library — all check functions + `check_nwbfile_for_consistency()` entry point |
| `widefield2025/_scripts/check_consistency.py` | CLI wrapper that imports the library and exposes `--raw` / `--processed` flags |

The library follows the same convention as Heberto Mayorquin's BWM checks in
`ibl_to_nwb/testing/_consistency_checks.py`.

---

## Usage

```bash
# single raw file
python src/ibl_widefield_to_nwb/widefield2025/_scripts/check_consistency.py \
    --raw /path/to/sub-X_ses-Y_desc-raw_behavior+ophys.nwb

# single processed file
python src/ibl_widefield_to_nwb/widefield2025/_scripts/check_consistency.py \
    --processed /path/to/sub-X_ses-Y_desc-processed_behavior+ophys.nwb

# both at once
python src/ibl_widefield_to_nwb/widefield2025/_scripts/check_consistency.py \
    --raw /path/to/raw.nwb \
    --processed /path/to/processed.nwb
```

The script exits with code `0` if all checks pass, `1` if any fail.

To run checks programmatically (e.g. in a test suite):

```python
from one.api import ONE
from ibl_widefield_to_nwb.widefield2025.testing._consistency_checks import check_nwbfile_for_consistency

one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international")
passed = check_nwbfile_for_consistency(one=one, nwbfile_path="/path/to/file.nwb")
```

---

## Check Catalogue

### Raw NWB checks

| Check | Data compared | Notes |
|---|---|---|
| `raw_imaging_timestamps` | `OnePhotonSeriesCalcium` / `OnePhotonSeriesIsosbestic` timestamps vs `imaging.times.npy` filtered by `imagingLightSource` | Stub-aware: truncates expected to NWB length when stub detected |
| `raw_imaging_data` | Pixel values in `OnePhotonSeries` vs frames decoded from `imaging.frames.mov` | Two-tier: structural always; `.mov` content check when file is cached locally |
| `raw_sync_events` | `LabeledEvents` timestamps/polarities vs `_spikeglx_sync.*` (DAQ sessions); monotonicity for all sessions | Content check skipped for NIDQ sessions (sync not re-extracted) |
| `raw_video_timestamps` | `ImageSeries` timestamps vs `_ibl_{camera}Camera.times.npy` | Skipped per camera if timestamps not in ONE |
| `mean_images` | `MeanImage` / `MeanImageIsosbestic` vs `widefieldChannels.frameAverage.npy` | Uses `imagingLightSource` to pick the right channel slice |

### Processed NWB checks

| Check | Data compared | Notes |
|---|---|---|
| `svd_spatial_components` | `PlaneSegmentation.image_mask` vs `widefieldU.images.npy` | Full check on first 3 components; random-sample check on 5 more |
| `svd_temporal_components` | `RoiResponseSeries.data` vs `widefieldSVT.uncorrected` / `haemoCorrected` | Wavelength-filtered; stub-aware (truncates expected) |
| `svd_timestamps` | `RoiResponseSeries.timestamps` vs `imaging.times.npy` filtered by wavelength | Stub-aware |
| `mean_images` | Same as raw (mean images also appear in processed files) | |
| `trials_data` | `nwbfile.trials` columns vs IBL trial tables via `SessionLoader` | Checks timing columns + reward volume + probability left |
| `wheel_data` | `WheelPosition` and `WheelMovementIntervals` vs `_ibl_wheel.*` / `_ibl_wheelMoves.*` | |
| `wheel_kinematics` | `WheelPositionSmoothed`, `WheelVelocitySmoothed`, `WheelAccelerationSmoothed` | Structural only (derived from wheel position; no ONE source) |
| `lick_data` | `EventsLickTimes.timestamps` vs `licks.times.npy` | Silently skipped if no lick module in file |
| `roi_motion_energy_data` | `{View}CameraMotionEnergy` data + timestamps vs ONE | Data load wrapped in try/except — some sessions lack this on the public API |
| `pupil_tracking_data` | Pupil diameter vs `_ibl_{view}Camera.features.pqt` | |
| `pose_estimation_data` | x, y, confidence vs `lightningPose.pqt` (DLC fallback) | |

### Optional checks (both file types)

These run for both raw and processed files whenever the corresponding data is present.

| Check | Condition | What is verified |
|---|---|---|
| `landmarks_data` | `"localization" in nwbfile.lab_meta_data` | `AtlasRegistration` exists; both coordinate images present; IBLBregma AP/ML within ±10 mm; CCFv3 values non-negative and within atlas extent; landmark count matches source JSON |
| `session_epochs` | `nwbfile.epochs is not None` | Non-empty; stop > start; non-negative; monotonically increasing |

---

## How `raw_imaging_data` Works

This check validates the full pipeline from `.mov` to NWB:

```
imaging.frames.mov
   └── cv2.VideoCapture + cv2.COLOR_BGR2GRAY   (same decode as build_frame_cache)
          └── gray_frame (H, W, uint8)
                 └── compare == nwbfile.acquisition["OnePhotonSeriesCalcium"].data[i]
```

**Channel selection** (how the per-wavelength frame position in the interleaved `.mov` is found):

1. `widefieldChannels.wiring.htsv` maps `LED channel_id → wavelength (nm)`
2. `widefieldEvents.raw.camlog` lists `#LED:<channel_id>,<frame_id>,<timestamp>` for every frame;
   `frame_id` (1-indexed) gives the position in the interleaved `.mov`
3. Filtering by `channel_id` gives the ordered list of `.mov` frame positions for that wavelength

**Sample strategy:** first 5 frames + 5 random frames are decoded and compared byte-for-byte.

**Tier 2 skipped when:**
- Session is not in the local ONE file cache (`one.eid2path()` returns `None`)
- `imaging.frames.mov` is not on disk
- `cv2` (OpenCV) is not installed

Tier 1 (structural checks) always runs regardless.

---

## Stub File Behaviour

Stub files contain only the first ~100 frames per channel (used for quick integration tests).
Sync signals and behavioral data in stub files cover the full session, so naive length checks fail.

The following checks handle this automatically:
- `raw_imaging_timestamps`: detects stub by comparing NWB frame count against ONE and truncates
  expected timestamps; skips the frame-trigger cross-check when stub is detected
- `svd_temporal_components` / `svd_timestamps`: always truncate expected to `n_nwb` rows,
  so they work for both stub and full files without special-casing

---

## Adding New Checks

1. Write a function with the signature `def _check_foo(*, nwbfile: NWBFile, one: ONE): ...`
   - Raise `AssertionError` (or any exception) on failure; return normally on success
   - Use `logger.debug(...)` for skip messages, `assert` / `assert_array_*` for failures
2. Register it in `check_nwbfile_for_consistency()`:
   - Add to the `checks` list for the appropriate file type(s), or use a conditional append
     for optional data (e.g. `if "my_module" in nwbfile.processing: checks.append(_check_foo)`)
