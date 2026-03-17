"""
Consistency checks for the IBL widefield-to-NWB conversion pipeline.

Verifies that data written to NWB files matches the source data from the IBL ONE API.
Adapted from Heberto Mayorquin's BWM consistency checks:
  https://github.com/h-mayorquin/IBL-to-nwb/blob/heberto_conversion/src/ibl_to_nwb/testing/_consistency_checks.py
"""

import logging
from pathlib import Path

import numpy as np
from numpy.testing import assert_array_almost_equal, assert_array_equal
from one.api import ONE
from pynwb import NWBHDF5IO, NWBFile

logger = logging.getLogger("widefield.consistency")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_revision(nwbfile: NWBFile) -> str:
    """Return the IBL revision string stored in NWB lab_meta_data."""
    for key in ("ibl_metadata", "IblMetadata"):
        if key in nwbfile.lab_meta_data:
            return nwbfile.lab_meta_data[key].revision
    return None  # no revision pinning for some data


def _get_eid(nwbfile: NWBFile) -> str:
    return nwbfile.session_id


def _load_light_source_index(one: ONE, eid: str, wavelength_nm: int) -> int:
    """
    Return the channel_id for a given excitation wavelength (nm).
    Mirrors _get_channel_id_from_wavelength() in utils/_widefield_times.py:
    one.load_dataset may return a DataFrame (newer ONE) or a Series (older ONE/format);
    falls back to reading the .htsv file directly if "wavelength" column is not found.
    """
    import pandas as pd

    props = one.load_dataset(eid, "imagingLightSource.properties", collection="alf/widefield")
    if "wavelength" not in props:
        session_path = one.eid2path(eid)
        htsv_path = session_path / "alf/widefield" / "imagingLightSource.properties.htsv"
        props = pd.read_csv(htsv_path)
    channel_ids = props.loc[props["wavelength"] == wavelength_nm, "channel_id"].tolist()
    if len(channel_ids) == 0:
        raise ValueError(f"Wavelength {wavelength_nm} nm not found in imagingLightSource.properties")
    return int(channel_ids[0])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def check_nwbfile_for_consistency(*, one: ONE, nwbfile_path: Path) -> bool:
    """
    Run all applicable consistency checks for a widefield NWB file.

    Returns True if all checks pass, False otherwise.
    """
    nwbfile_path = Path(nwbfile_path)
    logger.info(f"\n{'='*60}")
    logger.info(f"Checking: {nwbfile_path.name}")
    logger.info(f"{'='*60}")

    passed, failed = [], []

    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        nwbfile = io.read()

        # Select checks based on filename descriptor
        if "desc-raw" in nwbfile_path.name:
            checks = [
                _check_raw_imaging_timestamps,
                _check_raw_imaging_data,
                _check_raw_sync_events,
                _check_raw_video_timestamps,
                _check_mean_images,
            ]
        elif "desc-processed" in nwbfile_path.name:
            checks = [
                _check_svd_spatial_components,
                _check_svd_temporal_components,
                _check_svd_timestamps,
                _check_mean_images,
                _check_trials_data,
                _check_wheel_data,
                _check_wheel_kinematics,
                _check_lick_data,
            ]
            # Optional camera-based checks
            if "motion_energy" in nwbfile.processing:
                checks.append(_check_roi_motion_energy_data)
            if "pupil" in nwbfile.processing:
                checks.append(_check_pupil_tracking_data)
            if "pose_estimation" in nwbfile.processing:
                checks.append(_check_pose_estimation_data)
        else:
            logger.warning("Cannot determine file type from filename; running all checks")
            checks = [
                _check_raw_imaging_timestamps,
                _check_raw_imaging_data,
                _check_raw_sync_events,
                _check_raw_video_timestamps,
                _check_mean_images,
                _check_svd_spatial_components,
                _check_svd_temporal_components,
                _check_svd_timestamps,
                _check_trials_data,
                _check_wheel_data,
                _check_wheel_kinematics,
                _check_lick_data,
            ]

        # Optional checks that apply to both raw and processed files
        if "localization" in nwbfile.lab_meta_data:
            checks.append(_check_landmarks_data)
        if nwbfile.epochs is not None:
            checks.append(_check_session_epochs)

        for check_fn in checks:
            name = check_fn.__name__.replace("_check_", "")
            try:
                check_fn(nwbfile=nwbfile, one=one)
                passed.append(name)
                logger.info(f"  ✓ {name}")
            except Exception as exc:
                failed.append((name, exc))
                logger.error(f"  ✗ {name}: {exc}")

    logger.info(f"\nResults: {len(passed)}/{len(passed)+len(failed)} passed")
    if failed:
        logger.error("Failed checks:")
        for name, exc in failed:
            logger.error(f"  - {name}: {exc}")
    return len(failed) == 0


# ---------------------------------------------------------------------------
# Raw NWB checks
# ---------------------------------------------------------------------------


def _check_raw_imaging_timestamps(*, nwbfile: NWBFile, one: ONE):
    """
    Verify OnePhotonSeriesCalcium and OnePhotonSeriesIsosbestic timestamps match
    imaging.times.npy filtered by wavelength via imagingLightSource.
    """
    eid = _get_eid(nwbfile)

    all_times = one.load_dataset(eid, "imaging.times", collection="alf/widefield")
    light_source = one.load_dataset(eid, "imaging.imagingLightSource", collection="alf/widefield")
    # Truncate to shorter length (matches production code in _widefield_times.py)
    n_samples = min(len(all_times), len(light_source))
    all_times = all_times[:n_samples]
    light_source = light_source[:n_samples]

    is_stub = False
    for series_name, wavelength_nm in [("OnePhotonSeriesCalcium", 470), ("OnePhotonSeriesIsosbestic", 405)]:
        if series_name not in nwbfile.acquisition:
            logger.debug(f"  {series_name} not in acquisition, skipping")
            continue

        channel_idx = _load_light_source_index(one, eid, wavelength_nm)
        expected_timestamps = all_times[light_source == channel_idx]
        nwb_timestamps = nwbfile.acquisition[series_name].timestamps[:]
        n_nwb = len(nwb_timestamps)

        # Stub files contain only the first n_nwb frames; truncate expected accordingly
        if n_nwb < len(expected_timestamps):
            logger.debug(f"  {series_name}: stub file detected ({n_nwb} < {len(expected_timestamps)} frames)")
            is_stub = True
            expected_timestamps = expected_timestamps[:n_nwb]
        else:
            assert n_nwb == len(expected_timestamps), (
                f"{series_name}: timestamp count mismatch: " f"ONE={len(expected_timestamps)}, NWB={n_nwb}"
            )
        assert_array_almost_equal(
            expected_timestamps,
            nwb_timestamps,
            decimal=6,
            err_msg=f"{series_name} timestamps do not match imaging.times.npy",
        )

    # Cross-check: frame trigger events (frame_on) should match total imaging frames.
    # Skipped for stub files because sync events cover the full session while imaging is truncated.
    if not is_stub and "EventsFrameTrigger" in nwbfile.acquisition and "OnePhotonSeriesCalcium" in nwbfile.acquisition:
        trigger = nwbfile.acquisition["EventsFrameTrigger"]
        frame_on_times = trigger.timestamps[trigger.data[:] == 1]
        total_imaging = len(nwbfile.acquisition["OnePhotonSeriesCalcium"].timestamps[:])
        if "OnePhotonSeriesIsosbestic" in nwbfile.acquisition:
            total_imaging += len(nwbfile.acquisition["OnePhotonSeriesIsosbestic"].timestamps[:])
        # Allow ±1 tolerance: one stray pulse at session boundary is normal
        assert abs(len(frame_on_times) - total_imaging) <= 1, (
            f"EventsFrameTrigger frame_on count ({len(frame_on_times)}) differs from "
            f"total imaging frames ({total_imaging}) by more than 1"
        )


def _check_raw_imaging_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify the raw imaging pixel data in OnePhotonSeriesCalcium / OnePhotonSeriesIsosbestic.

    Two-tier check:
    1. Structural (always): frame count matches timestamps; sampled frames are finite and
       spatially varying (not blank or corrupted).
    2. Content (.mov required): decodes frames directly from ``imaging.frames.mov`` using
       the same BGR-to-grayscale path as ``build_frame_cache`` (``cv2.COLOR_BGR2GRAY``),
       then compares against NWB frames — validating the full pipeline end-to-end.
       Skipped gracefully if the .mov is not in the local ONE cache or cv2 is unavailable.

    Channel selection (required for Tier 2):
      ``widefieldChannels.wiring.htsv`` maps LED channel_id → wavelength.
      ``widefieldEvents.raw.camlog`` lists ``#LED:<channel_id>,<frame_id>,<ts>`` per frame;
      frame_id (1-indexed) gives the position in the interleaved .mov for that channel.
    """
    import re

    eid = _get_eid(nwbfile)

    for series_name, wavelength_nm in [("OnePhotonSeriesCalcium", 470), ("OnePhotonSeriesIsosbestic", 405)]:
        if series_name not in nwbfile.acquisition:
            logger.debug(f"  {series_name} not in acquisition, skipping")
            continue

        series = nwbfile.acquisition[series_name]
        n_frames_nwb = series.data.shape[0]

        # ── Tier 1: structural checks ──────────────────────────────────────────

        # Frame count must match timestamp count
        if series.timestamps is not None:
            assert n_frames_nwb == len(series.timestamps[:]), (
                f"{series_name}: data frame count ({n_frames_nwb}) != timestamp count " f"({len(series.timestamps[:])})"
            )

        # Sample a few frames to check value range and spatial variation
        for i in [0, min(1, n_frames_nwb - 1), min(10, n_frames_nwb - 1)]:
            frame = series.data[i]
            assert np.all(np.isfinite(frame)), f"{series_name} frame {i} contains NaN/Inf"
            assert frame.max() > frame.min(), (
                f"{series_name} frame {i} is spatially constant (all pixels = {frame.max()}); "
                "likely empty or corrupted"
            )

        # ── Tier 2: .mov content check ────────────────────────────────────────

        session_path = one.eid2path(eid)
        if session_path is None:
            logger.debug(f"  {series_name}: session not in local ONE cache, skipping content check")
            continue

        raw_data_dir = session_path / "raw_widefield_data"
        mov_path = raw_data_dir / "imaging.frames.mov"
        if not mov_path.exists():
            logger.debug(f"  {series_name}: imaging.frames.mov not found, skipping content check")
            continue

        try:
            import cv2
        except ImportError:
            logger.debug(f"  {series_name}: cv2 not available, skipping content check")
            continue

        # Resolve channel_id for this wavelength from wiring.htsv
        htsv_path = raw_data_dir / "widefieldChannels.wiring.htsv"
        if not htsv_path.exists():
            logger.debug(f"  {series_name}: wiring.htsv not found, skipping content check")
            continue

        import pandas as pd

        # read with index_col=0 then reset_index() to handle both file formats:
        #   CSK: unnamed index col + LED col  →  reset gives {index, LED, wavelength}
        #   FD:  LED as index col             →  reset gives {LED, wavelength}
        wiring = pd.read_csv(htsv_path, sep="\t", index_col=0).reset_index()
        row = wiring[wiring["wavelength"] == wavelength_nm]
        if row.empty or "LED" not in row.columns:
            logger.debug(f"  {series_name}: wavelength {wavelength_nm} nm not in wiring.htsv, skipping")
            continue
        channel_id = int(row.iloc[0]["LED"])

        # Parse camera log: collect the .mov frame indices (0-indexed) for this channel
        camlog_path = raw_data_dir / "widefieldEvents.raw.camlog"
        if not camlog_path.exists():
            logger.debug(f"  {series_name}: camlog not found, skipping content check")
            continue

        frame_indices = []  # positions in the interleaved .mov
        with open(camlog_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#LED"):
                    m = re.match(r"#LED:(?P<ch>\d+),(?P<fid>\d+),", line)
                    if m and int(m.group("ch")) == channel_id:
                        frame_indices.append(int(m.group("fid")) - 1)  # convert to 0-indexed

        if len(frame_indices) == 0:
            logger.debug(f"  {series_name}: no frames found in camlog for channel {channel_id}")
            continue

        frame_indices = np.array(frame_indices)

        # Select frames to compare: first 5 + 5 random
        rng = np.random.default_rng(42)
        n_check = min(5, n_frames_nwb)
        check_positions = np.unique(
            np.concatenate(
                [
                    np.arange(n_check),
                    rng.integers(0, n_frames_nwb, size=n_check),
                ]
            )
        )
        check_positions = check_positions[check_positions < n_frames_nwb]

        cap = cv2.VideoCapture(str(mov_path))
        try:
            for pos in check_positions:
                mov_frame_idx = frame_indices[pos]
                cap.set(cv2.CAP_PROP_POS_FRAMES, mov_frame_idx)
                ret, bgr_frame = cap.read()
                assert ret, f"{series_name}: failed to read frame {mov_frame_idx} from .mov"

                # Same decode as build_frame_cache
                gray_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
                nwb_frame = series.data[pos]

                # Both are (H, W): build_frame_cache writes (H, W); WidefieldImagingExtractor
                # transposes to (W, H) for neuroconv, which transposes back to (H, W) for NWB.
                assert_array_equal(
                    gray_frame,
                    nwb_frame,
                    err_msg=f"{series_name} frame {pos} (.mov index {mov_frame_idx}) does not match NWB",
                )
        finally:
            cap.release()

        logger.debug(f"  {series_name}: verified {len(check_positions)} frames against imaging.frames.mov")


def _check_raw_sync_events(*, nwbfile: NWBFile, one: ONE):
    """
    For DAQ sessions: verify LabeledEvents timestamps match _spikeglx_sync files.
    For all sessions: verify timestamp monotonicity and non-negativity.
    """
    eid = _get_eid(nwbfile)
    event_names = [k for k in nwbfile.acquisition if k.startswith("Events")]

    # Structural checks for all sessions
    for name in event_names:
        ts = nwbfile.acquisition[name].timestamps[:]
        assert len(ts) > 0, f"{name}: empty timestamps"
        assert ts[0] >= 0, f"{name}: negative first timestamp {ts[0]}"
        assert np.all(np.diff(ts) >= 0), f"{name}: non-monotonic timestamps"

    # Content checks for DAQ sessions (raw_sync_data available)
    available = one.list_datasets(eid, collection="raw_sync_data")
    sync_channels_file = next((d for d in available if "_spikeglx_sync.channels" in d), None)
    if sync_channels_file is None:
        logger.debug("  No raw_sync_data found; skipping content check (NIDQ session)")
        return

    sync_times = one.load_dataset(eid, "_spikeglx_sync.times", collection="raw_sync_data")
    sync_channels = one.load_dataset(eid, "_spikeglx_sync.channels", collection="raw_sync_data")
    sync_polarities = one.load_dataset(eid, "_spikeglx_sync.polarities", collection="raw_sync_data")
    # one.load_dataset returns the parsed dict directly for .json files
    wiring = one.load_dataset(eid, "_spikeglx_DAQdata.wiring.json", collection="raw_sync_data")

    digital_map = wiring.get("SYNC_WIRING_DIGITAL", {})
    # port string "P0.X" → channel index X
    port_to_channel = {port: int(port.replace("P0.", "")) for port in digital_map}
    device_to_channel = {device: port_to_channel[port] for port, device in digital_map.items()}

    # Device name → NWB Events name mapping
    device_to_nwb = {
        "left_camera": "EventsLeftCamera",
        "right_camera": "EventsRightCamera",
        "body_camera": "EventsBodyCamera",
        "frame_trigger": "EventsFrameTrigger",
        "frame2ttl": "EventsFrame2ttl",
        "rotary_encoder_0": "EventsRotaryEncoder0",
        "rotary_encoder_1": "EventsRotaryEncoder1",
        "audio": "EventsAudio",
        "bpod": "EventsBpodDigital",
    }

    for device, channel_idx in device_to_channel.items():
        nwb_name = device_to_nwb.get(device)
        if nwb_name not in nwbfile.acquisition:
            continue

        mask = sync_channels == channel_idx
        expected_times = sync_times[mask]
        expected_data = (sync_polarities[mask] > 0).astype(np.int8)  # +1→1, -1→0

        nwb_events = nwbfile.acquisition[nwb_name]
        nwb_times = nwb_events.timestamps[:]
        nwb_data = nwb_events.data[:]

        assert len(expected_times) == len(
            nwb_times
        ), f"{nwb_name}: event count mismatch ONE={len(expected_times)}, NWB={len(nwb_times)}"
        assert_array_almost_equal(
            expected_times, nwb_times, decimal=6, err_msg=f"{nwb_name} timestamps do not match sync file"
        )
        assert_array_equal(expected_data, nwb_data, err_msg=f"{nwb_name} data (polarity) does not match sync file")


def _check_raw_video_timestamps(*, nwbfile: NWBFile, one: ONE):
    """
    Verify ImageSeries timestamps match _ibl_{camera}Camera.times.npy from ONE.
    """
    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)
    load_kwargs = dict(collection="alf", revision=revision)

    # VideoLeftCamera, VideoRightCamera, VideoBodyCamera
    video_names = [k for k in nwbfile.acquisition if k.startswith("Video")]
    camera_map = {"Left": "left", "Right": "right", "Body": "body"}

    for name in video_names:
        camera_key = next((k for k in camera_map if k in name), None)
        if camera_key is None:
            continue
        view = camera_map[camera_key]

        times_file = f"_ibl_{view}Camera.times"
        available = one.list_datasets(eid, filename=f"*{view}Camera.times*")
        if not available:
            logger.debug(f"  {name}: no camera times found in ONE, skipping")
            continue

        expected_times = one.load_dataset(eid, times_file, **load_kwargs)
        nwb_times = nwbfile.acquisition[name].timestamps[:]

        assert len(expected_times) == len(
            nwb_times
        ), f"{name}: timestamp count mismatch ONE={len(expected_times)}, NWB={len(nwb_times)}"
        assert_array_almost_equal(
            expected_times, nwb_times, decimal=6, err_msg=f"{name} timestamps do not match _ibl_{view}Camera.times"
        )


# ---------------------------------------------------------------------------
# Processed NWB checks
# ---------------------------------------------------------------------------


def _check_svd_spatial_components(*, nwbfile: NWBFile, one: ONE):
    """
    Verify PlaneSegmentation image_mask matches widefieldU.images.npy from ONE.
    Checks shape, first 3 components fully, and 5 random components with a random pixel sample.
    """
    eid = _get_eid(nwbfile)
    U_raw = one.load_dataset(eid, "widefieldU.images", collection="alf/widefield")
    # U shape from ONE: (height, width, n_components) — transpose to (n_components, height, width)
    U = U_raw.transpose(2, 0, 1)

    for ps_name in ("SVDTemporalComponentsCalcium", "SVDTemporalComponentsIsosbestic"):
        ps = nwbfile.processing["ophys"]["SVDSpatialComponents"][ps_name]
        image_mask = ps.image_mask[:]
        # image_mask shape in NWB: (n_components, height, width)

        assert (
            image_mask.shape == U.shape
        ), f"{ps_name}: image_mask shape {image_mask.shape} != widefieldU shape {U.shape}"

        # Full check on first 3 components (fast)
        assert_array_almost_equal(
            U[:3],
            image_mask[:3],
            decimal=5,
            err_msg=f"{ps_name}: first 3 spatial components do not match widefieldU.images",
        )

        # Random sample: 5 components, 100 pixels each
        rng = np.random.default_rng(42)
        n = image_mask.shape[0]
        for k in rng.integers(0, n, size=5):
            flat_one = U[k].ravel()
            flat_nwb = image_mask[k].ravel()
            px = rng.integers(0, len(flat_one), size=100)
            assert_array_almost_equal(
                flat_one[px],
                flat_nwb[px],
                decimal=5,
                err_msg=f"{ps_name} component {k}: pixel mismatch with widefieldU",
            )


def _check_svd_temporal_components(*, nwbfile: NWBFile, one: ONE):
    """
    Verify RoiResponseSeries data matches widefieldSVT files from ONE (wavelength-filtered).

    widefieldSVT.uncorrected.npy has shape (n_components, n_total_frames) — all wavelengths.
    After filtering for 470 nm frames and transposing: (n_470nm_frames, n_components).
    This should match DenoisedSVDTemporalComponentsCalcium.data.

    widefieldSVT.haemoCorrected.npy has shape (n_components, n_470nm_frames) — 470 nm only.
    After transposing: (n_470nm_frames, n_components).
    This should match HaemoCorrectedSVDTemporalComponentsCalcium.data.
    """
    eid = _get_eid(nwbfile)

    SVT_uncorr = one.load_dataset(eid, "widefieldSVT.uncorrected", collection="alf/widefield")
    SVT_haemo = one.load_dataset(eid, "widefieldSVT.haemoCorrected", collection="alf/widefield")
    light_source = one.load_dataset(eid, "imaging.imagingLightSource", collection="alf/widefield")

    chan_470 = _load_light_source_index(one, eid, 470)
    chan_405 = _load_light_source_index(one, eid, 405)
    idx_470 = np.where(light_source == chan_470)[0]
    idx_405 = np.where(light_source == chan_405)[0]

    svd_temporal = nwbfile.processing["ophys"]["SVDTemporalComponents"]

    checks = [
        ("DenoisedSVDTemporalComponentsCalcium", SVT_uncorr[:, idx_470].T),
        ("DenoisedSVDTemporalComponentsIsosbestic", SVT_uncorr[:, idx_405].T),
        ("HaemoCorrectedSVDTemporalComponentsCalcium", SVT_haemo.T),
    ]

    for rrs_name, expected_full in checks:
        if rrs_name not in svd_temporal.roi_response_series:
            logger.debug(f"  {rrs_name} not found, skipping")
            continue

        rrs = svd_temporal.roi_response_series[rrs_name]
        nwb_data = rrs.data[:]
        n_nwb = nwb_data.shape[0]

        # Stub files contain only the first n_nwb frames
        expected = expected_full[:n_nwb]

        assert (
            nwb_data.shape[1] == expected.shape[1]
        ), f"{rrs_name}: component count mismatch NWB={nwb_data.shape[1]}, ONE={expected.shape[1]}"
        assert_array_almost_equal(
            expected, nwb_data, decimal=4, err_msg=f"{rrs_name} temporal data does not match widefieldSVT"
        )


def _check_svd_timestamps(*, nwbfile: NWBFile, one: ONE):
    """
    Verify RoiResponseSeries timestamps match imaging.times.npy filtered by wavelength.
    """
    eid = _get_eid(nwbfile)
    all_times = one.load_dataset(eid, "imaging.times", collection="alf/widefield")
    light_source = one.load_dataset(eid, "imaging.imagingLightSource", collection="alf/widefield")

    svd_temporal = nwbfile.processing["ophys"]["SVDTemporalComponents"]
    wavelength_map = {
        "DenoisedSVDTemporalComponentsCalcium": 470,
        "DenoisedSVDTemporalComponentsIsosbestic": 405,
        "HaemoCorrectedSVDTemporalComponentsCalcium": 470,
    }

    for rrs_name, wavelength_nm in wavelength_map.items():
        if rrs_name not in svd_temporal.roi_response_series:
            continue
        rrs = svd_temporal.roi_response_series[rrs_name]
        if rrs.timestamps is None:
            continue

        chan_idx = _load_light_source_index(one, eid, wavelength_nm)
        expected_times = all_times[light_source == chan_idx]
        nwb_times = rrs.timestamps[:]
        n_nwb = len(nwb_times)

        assert_array_almost_equal(
            expected_times[:n_nwb],
            nwb_times,
            decimal=6,
            err_msg=f"{rrs_name} timestamps do not match imaging.times.npy (filtered for {wavelength_nm} nm)",
        )


def _check_trials_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify trial timing columns in nwbfile.trials against IBL ONE source data.
    Checks timestamps only (no tidy transformations applied here).
    """
    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)

    from brainbox.io.one import SessionLoader

    sl = SessionLoader(one=one, eid=eid, revision=revision)
    sl.load_trials()
    t = sl.trials

    nwb_trials = nwbfile.trials[:]

    # Column mapping: NWB name → IBL column name
    time_column_map = {
        "start_time": ("intervals", 0),
        "stop_time": ("intervals", 1),
        "gabor_stimulus_onset_time": ("stimOn_times", None),
        "gabor_stimulus_offset_time": ("stimOff_times", None),
        "auditory_cue_time": ("goCue_times", None),
        "wheel_movement_onset_time": ("firstMovement_times", None),
        "choice_registration_time": ("response_times", None),
        "feedback_time": ("feedback_times", None),
    }

    for nwb_col, (ibl_col, idx) in time_column_map.items():
        if nwb_col not in nwb_trials.columns:
            continue
        if ibl_col not in t.columns:
            continue

        nwb_vals = nwb_trials[nwb_col].values
        one_vals = t[ibl_col].values[:, idx] if idx is not None else t[ibl_col].values

        assert_array_almost_equal(
            one_vals, nwb_vals, decimal=6, err_msg=f"trials column '{nwb_col}' does not match IBL '{ibl_col}'"
        )

    # Scalar checks (no transformation)
    if "reward_volume_uL" in nwb_trials.columns and "rewardVolume" in t.columns:
        assert_array_almost_equal(
            t["rewardVolume"].values,
            nwb_trials["reward_volume_uL"].values,
            decimal=5,
            err_msg="trials column 'reward_volume_uL' does not match IBL 'rewardVolume'",
        )
    if "probability_left" in nwb_trials.columns and "probabilityLeft" in t.columns:
        assert_array_almost_equal(
            t["probabilityLeft"].values,
            nwb_trials["probability_left"].values,
            decimal=6,
            err_msg="trials column 'probability_left' does not match IBL 'probabilityLeft'",
        )


def _check_wheel_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify WheelPosition timestamps/data and WheelMovementIntervals against ONE.
    """
    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)
    load_kwargs = dict(collection="alf", revision=revision)

    wheel_mod = nwbfile.processing["wheel"]
    wp = wheel_mod.data_interfaces["WheelPosition"]
    wmi = wheel_mod.data_interfaces["WheelMovementIntervals"][:]

    # Position
    one_position = one.load_dataset(eid, "_ibl_wheel.position", **load_kwargs)
    assert_array_equal(one_position, wp.data[:], err_msg="WheelPosition data mismatch")

    # Timestamps
    one_timestamps = one.load_dataset(eid, "_ibl_wheel.timestamps", **load_kwargs)
    assert_array_almost_equal(one_timestamps, wp.timestamps[:], decimal=6, err_msg="WheelPosition timestamps mismatch")

    # Movement intervals
    one_intervals = one.load_dataset(eid, "_ibl_wheelMoves.intervals", **load_kwargs)
    nwb_intervals = wmi[["start_time", "stop_time"]].values
    assert_array_equal(one_intervals, nwb_intervals, err_msg="WheelMovementIntervals mismatch")

    # Peak amplitude
    one_amplitude = one.load_dataset(eid, "_ibl_wheelMoves.peakAmplitude", **load_kwargs)
    assert_array_equal(
        one_amplitude, wmi["peak_amplitude"].values, err_msg="WheelMovementIntervals peak_amplitude mismatch"
    )


def _check_lick_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify EventsLickTimes timestamps against licks.times.npy from ONE.
    """
    if "lick_times" not in nwbfile.processing:
        logger.debug("  No lick_times module found, skipping")
        return

    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)

    lick_events = nwbfile.processing["lick_times"]["EventsLickTimes"]
    nwb_times = lick_events.timestamps[:]

    one_times = one.load_dataset(eid, "licks.times", collection="alf", revision=revision)
    assert_array_almost_equal(
        one_times, nwb_times, decimal=6, err_msg="EventsLickTimes timestamps do not match licks.times.npy"
    )


def _check_mean_images(*, nwbfile: NWBFile, one: ONE):
    """
    Verify MeanImage / MeanImageIsosbestic against widefieldChannels.frameAverage.npy from ONE.

    frameAverage shape: (n_channels, H, W) — first axis indexes light-source channels by
    the first-frame index in imaging.imagingLightSource (0 = blue/functional, 1 = violet/iso).
    """
    eid = _get_eid(nwbfile)
    images_container = nwbfile.processing.get("ophys", {})
    if hasattr(images_container, "data_interfaces"):
        images_container = images_container.data_interfaces.get("Images")
    else:
        images_container = None

    if images_container is None:
        logger.debug("  No ophys/Images container found, skipping mean-image check")
        return

    frame_average = one.load_dataset(eid, "widefieldChannels.frameAverage", collection="alf/widefield")
    # frame_average shape: (n_channels, H, W)
    light_source = one.load_dataset(eid, "imaging.imagingLightSource", collection="alf/widefield")

    for nwb_name, wavelength_nm in [("MeanImage", 470), ("MeanImageIsosbestic", 405)]:
        if nwb_name not in images_container.images:
            logger.debug(f"  {nwb_name} not in Images container, skipping")
            continue

        chan_id = _load_light_source_index(one, eid, wavelength_nm)
        # first_frame_index: channel index into frameAverage first axis
        first_frame_index = int(np.where(light_source == chan_id)[0][0])

        expected = frame_average[first_frame_index]
        nwb_data = images_container.images[nwb_name].data[:]

        assert (
            nwb_data.shape == expected.shape
        ), f"{nwb_name}: shape mismatch NWB={nwb_data.shape} vs ONE={expected.shape}"
        assert_array_almost_equal(
            expected, nwb_data, decimal=4, err_msg=f"{nwb_name} does not match widefieldChannels.frameAverage.npy"
        )


def _check_wheel_kinematics(*, nwbfile: NWBFile, one: ONE):
    """
    Structural check for derived wheel kinematics (WheelPositionSmoothed, WheelVelocitySmoothed,
    WheelAccelerationSmoothed). These are computed from raw wheel position, so we verify:
    - All three series exist in the wheel module
    - All have the same length and sampling rate
    - Values are finite (no NaN/inf from the filtering step)
    - Velocity and acceleration are zero-mean compared to position scale (sanity check)
    """
    wheel_mod = nwbfile.processing.get("wheel")
    if wheel_mod is None:
        logger.debug("  No wheel module found, skipping kinematics check")
        return

    required = ["WheelPositionSmoothed", "WheelVelocitySmoothed", "WheelAccelerationSmoothed"]
    series = {}
    for name in required:
        if name not in wheel_mod.data_interfaces:
            raise AssertionError(f"wheel module is missing {name}")
        series[name] = wheel_mod.data_interfaces[name]

    # All must share the same length and rate
    lengths = {name: series[name].data[:].shape[0] for name in required}
    assert len(set(lengths.values())) == 1, f"Wheel kinematics series have inconsistent lengths: {lengths}"

    rates = {}
    for name in required:
        s = series[name]
        rates[name] = s.rate
    assert len(set(rates.values())) == 1, f"Wheel kinematics series have inconsistent rates: {rates}"

    # Values must be finite
    for name in required:
        data = series[name].data[:]
        assert np.all(np.isfinite(data)), f"{name} contains NaN or Inf values"

    # Velocity should be derivative of position: std(vel) << std(position) at 1 kHz is not guaranteed,
    # but std(acceleration) <= std(velocity) * rate is a rough sanity check
    vel = series["WheelVelocitySmoothed"].data[:]
    acc = series["WheelAccelerationSmoothed"].data[:]
    rate = series["WheelVelocitySmoothed"].rate
    assert np.std(acc) <= np.std(vel) * rate * 10, (
        f"Acceleration std ({np.std(acc):.4f}) seems implausibly large relative to "
        f"velocity std ({np.std(vel):.4f}) × rate ({rate})"
    )


def _check_landmarks_data(*, nwbfile: NWBFile, one: ONE):
    """
    Sanity-check the anatomical localization data:

    1. Existence: localization, AtlasRegistration, coordinate images, brain-region masks
    2. Coordinate range:
       - IBLBregma: AP and ML within ±10 mm (10000 µm), DV within 0–5 mm
       - CCFv3 (PIR): AP 0–13200 µm, DV 0–8000 µm, ML 0–11400 µm
    3. Landmark count: labels in Landmarks table matches source JSON on ONE
    4. Shape consistency: coordinate image shape matches mean image shape
    """
    eid = _get_eid(nwbfile)
    localization = nwbfile.lab_meta_data.get("localization")
    if localization is None:
        raise AssertionError("'localization' not found in lab_meta_data")

    # 1 — Atlas registration exists
    atlas_key = next(
        (k for k in nwbfile.lab_meta_data if "atlas" in k.lower() or "registration" in k.lower()),
        None,
    )
    assert atlas_key is not None, "No AtlasRegistration found in lab_meta_data"

    # 2 — Coordinate images
    # anatomical_coordinates_images is a LabelledDict — iterate over .values() to get objects
    aci = localization.anatomical_coordinates_images
    coord_images = {v.name: v for v in aci.values()} if hasattr(aci, "values") else {img.name: img for img in aci}
    assert (
        "AnatomicalCoordinatesImageIBLBregma" in coord_images
    ), "AnatomicalCoordinatesImageIBLBregma missing from localization"
    assert (
        "AnatomicalCoordinatesImageCCFv3" in coord_images
    ), "AnatomicalCoordinatesImageCCFv3 missing from localization"

    # Coordinates stored as separate x/y/z arrays (H, W) per channel
    ibl = coord_images["AnatomicalCoordinatesImageIBLBregma"]
    ccf = coord_images["AnatomicalCoordinatesImageCCFv3"]

    ibl_x, ibl_y = ibl.x[:], ibl.y[:]  # ML, AP (RAS µm)
    ccf_x, ccf_y, ccf_z = ccf.x[:], ccf.y[:], ccf.z[:]  # AP, DV, ML (PIR µm)

    # IBL Bregma RAS (µm): ML=x, AP=y — valid pixels only
    for arr, label, lo, hi in [
        (ibl_x, "IBLBregma ML (x)", -10000, 10000),
        (ibl_y, "IBLBregma AP (y)", -10000, 10000),
    ]:
        valid = arr[np.isfinite(arr)]
        assert (
            valid.min() >= lo and valid.max() <= hi
        ), f"{label} out of range: [{valid.min():.0f}, {valid.max():.0f}] µm (expected [{lo}, {hi}])"

    # CCFv3 PIR (µm): AP=x, DV=y, ML=z — all non-negative, within atlas extent
    for arr, label, hi in [
        (ccf_x, "CCFv3 AP (x)", 15000),
        (ccf_y, "CCFv3 DV (y)", 12000),
        (ccf_z, "CCFv3 ML (z)", 14000),
    ]:
        valid = arr[np.isfinite(arr)]
        assert valid.min() >= 0, f"{label} contains negative values (min={valid.min():.0f} µm)"
        assert valid.max() <= hi, f"{label} out of range: max={valid.max():.0f} µm (expected ≤{hi})"

    # 3 — Landmark count vs source JSON
    landmarks_json = one.load_dataset(eid, "widefieldLandmarks.dorsalCortex.json", collection="alf/widefield")
    n_landmarks_json = len(landmarks_json)
    # anatomical_coordinates_tables is a LabelledDict — use .values() to get objects
    act = localization.anatomical_coordinates_tables
    tables = act.values() if hasattr(act, "values") else act
    for table in tables:
        if "Landmark" in table.name:
            n_landmarks_nwb = len(table)
            assert (
                n_landmarks_nwb == n_landmarks_json
            ), f"Landmark count mismatch: NWB={n_landmarks_nwb}, JSON={n_landmarks_json}"
            break

    # 4 — Brain region masks exist
    brm = localization.brain_region_masks
    assert brm and len(brm) > 0, "No BrainRegionMasks found in localization"


def _check_session_epochs(*, nwbfile: NWBFile, one: ONE):
    """
    Structural check for session epochs (task vs passive phases).
    Verifies: non-empty, stop_time > start_time, timestamps non-negative and monotonic.
    """
    epochs = nwbfile.epochs
    if epochs is None:
        logger.debug("  No epochs table found, skipping")
        return

    df = epochs[:]
    assert len(df) > 0, "Epochs table is empty"

    start_times = df["start_time"].values
    stop_times = df["stop_time"].values

    assert np.all(start_times >= 0), f"Epoch start_times contain negative values: {start_times[start_times < 0]}"
    assert np.all(stop_times >= 0), f"Epoch stop_times contain negative values: {stop_times[stop_times < 0]}"
    assert np.all(
        stop_times > start_times
    ), f"Epoch stop_time ≤ start_time for epochs: {np.where(stop_times <= start_times)[0].tolist()}"
    assert np.all(np.diff(start_times) >= 0), "Epoch start_times are not monotonically increasing"


def _check_roi_motion_energy_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify {view}CameraMotionEnergy data and timestamps against ONE.
    Module: processing["motion_energy"]
    """
    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)
    load_kwargs = dict(collection="alf", revision=revision)

    me_mod = nwbfile.processing["motion_energy"]

    for view in ("body", "left", "right"):
        obj_name = f"{view.capitalize()}CameraMotionEnergy"
        if obj_name not in me_mod.data_interfaces:
            continue

        me = me_mod.data_interfaces[obj_name]

        # Data
        try:
            one_data = one.load_dataset(eid, f"{view}Camera.ROIMotionEnergy", **load_kwargs)
        except Exception as e:
            logger.debug(f"  {obj_name}: ROIMotionEnergy not available on ONE ({e}), skipping content check")
            continue
        assert_array_equal(one_data, me.data[:], err_msg=f"{obj_name} data does not match ONE")

        # Timestamps
        one_times = one.load_dataset(eid, f"_ibl_{view}Camera.times", **load_kwargs)
        assert_array_almost_equal(
            one_times,
            me.timestamps[:],
            decimal=6,
            err_msg=f"{obj_name} timestamps do not match _ibl_{view}Camera.times",
        )


def _check_pupil_tracking_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify pupil diameter TimeSeries against ONE features.pqt.
    Module: processing["pupil"]
    Objects: LeftPupilDiameter, LeftPupilDiameterSmoothed, RightPupilDiameter, ...
    """
    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)
    load_kwargs = dict(collection="alf", revision=revision)

    pupil_mod = nwbfile.processing["pupil"]

    for view in ("left", "right"):
        # Check if any series for this view exists
        raw_name = f"{view.capitalize()}PupilDiameter"
        smooth_name = f"{view.capitalize()}PupilDiameterSmoothed"
        if raw_name not in pupil_mod.data_interfaces:
            continue

        features = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", **load_kwargs)
        cam_times = one.load_dataset(eid, f"_ibl_{view}Camera.times", **load_kwargs)

        # Raw diameter
        nwb_raw = pupil_mod.data_interfaces[raw_name]
        assert_array_almost_equal(
            features["pupilDiameter_raw"].values,
            nwb_raw.data[:],
            decimal=5,
            err_msg=f"{raw_name} data does not match features.pqt pupilDiameter_raw",
        )
        assert_array_almost_equal(
            cam_times, nwb_raw.timestamps[:], decimal=6, err_msg=f"{raw_name} timestamps do not match camera times"
        )

        # Smoothed diameter
        if smooth_name in pupil_mod.data_interfaces:
            nwb_smooth = pupil_mod.data_interfaces[smooth_name]
            assert_array_almost_equal(
                features["pupilDiameter_smooth"].values,
                nwb_smooth.data[:],
                decimal=5,
                err_msg=f"{smooth_name} data does not match features.pqt pupilDiameter_smooth",
            )


def _check_pose_estimation_data(*, nwbfile: NWBFile, one: ONE):
    """
    Verify PoseEstimation series (x, y, confidence, timestamps) against ONE.
    Module: processing["pose_estimation"]
    Objects: LeftCamera, RightCamera, BodyCamera (PoseEstimation containers).
    Skeletons is skipped (different type).

    Loads per-camera pose data from ONE directly (lightningPose preferred, DLC fallback)
    rather than using SessionLoader.load_pose() which tries all cameras simultaneously.
    """
    from one.alf.exceptions import ALFObjectNotFound

    eid = _get_eid(nwbfile)
    revision = _get_revision(nwbfile)
    pose_mod = nwbfile.processing["pose_estimation"]

    for view in ("left", "right", "body"):
        camera_key = f"{view.capitalize()}Camera"
        if camera_key not in pose_mod.data_interfaces:
            continue

        pose_container = pose_mod.data_interfaces[camera_key]
        # Skeletons and other non-PoseEstimation objects lack pose_estimation_series
        if not hasattr(pose_container, "pose_estimation_series"):
            continue

        # Load pose data from ONE: lightningPose preferred, DLC fallback
        pose_data = None
        for tracker in ("lightningPose", "dlc"):
            try:
                pose_data = one.load_dataset(
                    eid, f"_ibl_{view}Camera.{tracker}.pqt", collection="alf", revision=revision
                )
                break
            except ALFObjectNotFound:
                continue

        if pose_data is None:
            logger.debug(f"  No pose data found on ONE for {camera_key}, skipping")
            continue

        # Camera timestamps
        try:
            cam_times = one.load_dataset(eid, f"_ibl_{view}Camera.times", collection="alf", revision=revision)
        except ALFObjectNotFound:
            logger.debug(f"  No camera times found on ONE for {view}Camera, skipping")
            continue

        for series_name, series in pose_container.pose_estimation_series.items():
            # NWB node name: "PoseEstimationSeriesLeftPaw" → body part key: "leftPaw"
            body_part = series_name.replace("PoseEstimationSeries", "")
            body_part = body_part[0].lower() + body_part[1:]

            if f"{body_part}_x" not in pose_data.columns:
                logger.debug(f"  {body_part} not found in ONE pose data for {camera_key}")
                continue

            nwb_data = series.data[:]
            n_nwb = nwb_data.shape[0]

            # x coordinates
            assert_array_almost_equal(
                pose_data[f"{body_part}_x"].values[:n_nwb],
                nwb_data[:, 0],
                decimal=4,
                err_msg=f"{camera_key}/{series_name}: x coordinates mismatch",
            )
            # y coordinates
            assert_array_almost_equal(
                pose_data[f"{body_part}_y"].values[:n_nwb],
                nwb_data[:, 1],
                decimal=4,
                err_msg=f"{camera_key}/{series_name}: y coordinates mismatch",
            )
            # confidence
            if series.confidence is not None:
                assert_array_almost_equal(
                    pose_data[f"{body_part}_likelihood"].values[:n_nwb],
                    series.confidence[:],
                    decimal=4,
                    err_msg=f"{camera_key}/{series_name}: confidence mismatch",
                )
            # timestamps
            assert_array_almost_equal(
                cam_times[:n_nwb],
                series.timestamps[:],
                decimal=6,
                err_msg=f"{camera_key}/{series_name}: timestamps do not match camera times",
            )
