"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import time
from pathlib import Path

from ibl_to_nwb.datainterfaces import RawVideoInterface, SessionEpochsInterface
from ibl_to_nwb.utils import sanitize_subject_id_for_dandi
from ndx_ibl import IblMetadata, IblSubject
from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from one.api import ONE
from pynwb import NWBFile, read_nwb

from ibl_widefield_to_nwb.widefield2025 import WidefieldRawNWBConverter
from ibl_widefield_to_nwb.widefield2025.conversion import (
    build_frame_cache,
    validate_cache,
)
from ibl_widefield_to_nwb.widefield2025.datainterfaces import (
    IblNIDQInterface,
    IblWidefieldDAQInterface,
    IblWidefieldLandmarksInterface,
    WidefieldImagingInterface,
)


def convert_raw_session(
    eid: str,
    one: ONE,
    nwbfiles_folder_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    force_cache: bool = False,
    stub_test: bool = False,
) -> Path:
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    eid: str
        Experiment ID (session UUID).
    one: ONE
        An instance of the ONE API to access data.
    nwbfiles_folder_path: str or Path
        The folder path where the NWB file will be saved. The final NWB file will be saved as:
        {nwbfiles_folder_path}/{full|stub}/sub-{subject_id}/sub-{subject_id}_ses-{eid}_desc-raw_behavior+ophys.nwb
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional (calcium) imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

    Returns
    -------
    Path
        Path to the generated NWB file.
    """

    nwbfiles_folder_path = Path(nwbfiles_folder_path)

    # Setup paths
    session_info = one.alyx.rest("sessions", "read", id=eid)
    subject_nickname = session_info.get("subject")
    if isinstance(subject_nickname, dict):
        subject_nickname = subject_nickname.get("nickname") or subject_nickname.get("name")
    if not subject_nickname:
        subject_nickname = "unknown"

    # Sanitize subject nickname for DANDI compliance (replace underscores with hyphens)
    subject_id_for_filenames = sanitize_subject_id_for_dandi(subject_nickname)

    # New structure: nwbfiles/{full|stub}/sub-{subject}/*.nwb
    conversion_mode = "stub" if stub_test else "full"
    output_dir = nwbfiles_folder_path / conversion_mode / f"sub-{subject_id_for_filenames}"
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-{subject_id_for_filenames}_ses-{eid}_desc-raw_behavior+ophys.nwb"

    # ========================================================================
    # STEP 1: Download raw widefield files and build frame cache
    # ========================================================================

    # Ensure raw widefield files are in the local ONE cache before building the frame cache.
    # The frame cache builder reads the .mov file directly from disk and cannot use lazy ONE downloads.
    WidefieldImagingInterface.download_data(one=one, eid=eid, download_only=True)

    raw_data_dir_path = one.eid2path(eid) / "raw_widefield_data"
    cache_dir_path = raw_data_dir_path / "wf_cache"

    build_frame_cache(folder_path=raw_data_dir_path, cache_folder_path=cache_dir_path, overwrite=force_cache)
    validate_cache(cache_folder_path=cache_dir_path)

    # ========================================================================
    # STEP 2: Define data interfaces and conversion options
    # ========================================================================

    data_interfaces = dict()
    conversion_options = dict()

    # Add Imaging
    functional_imaging_interface = WidefieldImagingInterface(
        one=one,
        session=eid,
        cache_folder_path=cache_dir_path,
        excitation_wavelength_nm=functional_wavelength_nm,
    )
    data_interfaces.update(ImagingBlue=functional_imaging_interface)

    conversion_options.update(
        dict(
            ImagingBlue=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=0,
                stub_test=stub_test,
                iterator_options=dict(
                    display_progress=True,
                    progress_bar_options=dict(desc="Writing raw imaging data for functional channel..."),
                ),
            )
        )
    )

    isosbestic_imaging_interface = WidefieldImagingInterface(
        one=one,
        session=eid,
        cache_folder_path=cache_dir_path,
        excitation_wavelength_nm=isosbestic_wavelength_nm,
    )
    data_interfaces.update(ImagingViolet=isosbestic_imaging_interface)
    conversion_options.update(
        dict(
            ImagingViolet=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=1,
                stub_test=stub_test,
                iterator_options=dict(
                    display_progress=True,
                    progress_bar_options=dict(desc="Writing raw imaging data for isosbestic channel..."),
                ),
            )
        )
    )

    # Add sync data
    if IblNIDQInterface.check_availability(one=one, eid=eid)["available"]:
        data_interfaces["NIDQ"] = IblNIDQInterface(one=one, session=eid)
        conversion_options.update({"NIDQ": dict(stub_test=stub_test)})

    elif IblWidefieldDAQInterface.check_availability(one=one, eid=eid)["available"]:
        data_interfaces["DAQ"] = IblWidefieldDAQInterface(one=one, session=eid)
        conversion_options.update({"DAQ": dict(stub_test=stub_test)})
    else:
        print(f"No NIDQ sync data available for session '{eid}', skipping.")

    # Add raw behavioral video
    for camera_view in ["left", "right", "body"]:
        has_timestamps = bool(one.list_datasets(eid=eid, filename=f"*{camera_view}Camera.times*"))
        has_video = bool(one.list_datasets(eid=eid, filename=f"*{camera_view}Camera.raw.mp4*"))
        if not has_timestamps or not has_video:
            continue

        if stub_test:
            # In stub mode avoid triggering large downloads — only include if already cached
            session_path = one.eid2path(eid)
            if (
                session_path is None
                or not (session_path / f"raw_video_data/_iblrig_{camera_view}Camera.raw.mp4").exists()
            ):
                print(f"Stub mode: {camera_view}Camera video not in cache, skipping.")
                continue

        result = RawVideoInterface.check_availability(one=one, eid=eid, camera_name=camera_view)
        if result["available"]:
            # Pre-download workaround: RawVideoInterface accesses ALF camera files during __init__,
            # so all required files must be local before the interface is instantiated.
            try:
                one.load_object(id=eid, obj=f"{camera_view}Camera", collection="alf", download_only=True)
            except Exception as e:
                print(f"Failed to load raw video data for camera '{camera_view}' in session '{eid}': {e}")
                continue
            data_interfaces[f"RawVideo_{camera_view}"] = RawVideoInterface(
                camera_name=camera_view,
                one=one,
                session=eid,
                subject_id=subject_id_for_filenames,
                nwbfiles_folder_path=nwbfiles_folder_path / conversion_mode,
            )
        else:
            print(f"Missing data for '{camera_view}Camera': {result['missing_required']}")

    # Session epochs (high-level task vs passive phases)
    if SessionEpochsInterface.check_availability(one, eid)["available"]:
        data_interfaces["SessionEpochs"] = SessionEpochsInterface(one=one, session=eid)

    # Add Landmarks
    if IblWidefieldLandmarksInterface.check_availability(one=one, eid=eid)["available"]:
        data_interfaces["Landmarks"] = IblWidefieldLandmarksInterface(one=one, session=eid)
        conversion_options.update(dict(Landmarks=dict()))

    # ========================================================================
    # STEP 4: Create converter
    # ========================================================================

    converter = WidefieldRawNWBConverter(
        one=one,
        session=eid,
        data_interfaces=data_interfaces,
    )

    # ========================================================================
    # STEP 5: Get metadata
    # ========================================================================

    # Add datetime to conversion
    metadata = converter.get_metadata()

    # Use IBL-specific Subject metadata to populate NWBFile subject field
    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision="2025-05-06"))

    # ========================================================================
    # STEP 6: Write NWB file to disk
    # ========================================================================

    print(f"Writing to NWB '{nwbfile_path}' ...")
    conversion_start = time.time()

    converter.temporally_align_data_interfaces(metadata=metadata, conversion_options=conversion_options)
    converter.add_to_nwbfile(
        nwbfile=nwbfile,
        metadata=metadata,
        conversion_options=conversion_options,
    )

    # Get default backend configuration
    backend_configuration = get_default_backend_configuration(nwbfile=nwbfile, backend="hdf5")
    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend_configuration=backend_configuration,
    )

    nwbfile = read_nwb(nwbfile_path)
    print(nwbfile.acquisition)

    conversion_time = time.time() - conversion_start

    # Calculate total size
    total_size_bytes = nwbfile_path.stat().st_size
    total_size_gb = total_size_bytes / (1024**3)

    print(f"Conversion completed in {int(conversion_time // 60)}:{conversion_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({nwbfile_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return nwbfile_path
