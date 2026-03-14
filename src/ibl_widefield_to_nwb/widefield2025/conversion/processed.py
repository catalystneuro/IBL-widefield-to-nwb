import re
import time
from pathlib import Path

import ndx_anatomical_localization  # noqa: F401 — registers the NWB extension
from ibl_to_nwb.datainterfaces import (
    BrainwideMapTrialsInterface,
    IblPoseEstimationInterface,
    LickInterface,
    PassiveIntervalsInterface,
    PassiveReplayStimInterface,
    PassiveRFMInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    SessionEpochsInterface,
    WheelKinematicsInterface,
    WheelMovementsInterface,
    WheelPositionInterface,
)
from ibl_to_nwb.utils import sanitize_subject_id_for_dandi
from ndx_ibl import IblMetadata, IblSubject
from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from one.api import ONE
from pynwb import NWBFile

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter
from ibl_widefield_to_nwb.widefield2025.datainterfaces import (
    IblWidefieldLandmarksInterface,
    WidefieldSVDInterface,
)


def convert_processed_session(
    eid: str,
    one: ONE,
    nwbfiles_folder_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    stub_test: bool = False,
) -> Path:
    """
    Convert a single session of processed widefield imaging data to NWB format.

    Data is fetched directly from the ONE API (collection ``alf/widefield``); no local
    directory path is required.

    Parameters
    ----------
    eid: str
        Experiment ID (session UUID).
    one: ONE
        An instance of the ONE API to access data.
    nwbfiles_folder_path: str or Path
        The folder path where the NWB file will be saved.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    stub_test: bool, default: False
        Whether to run a stub test (process a smaller subset of data for testing purposes).

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

    subject_id_for_filenames = sanitize_subject_id_for_dandi(subject_nickname)

    conversion_mode = "stub" if stub_test else "full"
    output_dir = nwbfiles_folder_path / conversion_mode / f"sub-{subject_id_for_filenames}"
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-{subject_id_for_filenames}_ses-{eid}_desc-processed_behavior+ophys.nwb"

    # ========================================================================
    # STEP 1: Define data interfaces and conversion options
    # ========================================================================

    data_interfaces = dict()
    conversion_options = dict()
    interface_kwargs = dict(one=one, session=eid)

    # Add SVD interfaces
    data_interfaces["SVDCalcium"] = WidefieldSVDInterface(
        **interface_kwargs, excitation_wavelength_nm=functional_wavelength_nm
    )
    data_interfaces["SVDIsosbestic"] = WidefieldSVDInterface(
        **interface_kwargs, excitation_wavelength_nm=isosbestic_wavelength_nm
    )

    processed_data_conversion_options = dict(
        stub_test=stub_test,
        include_roi_centroids=False,
        include_roi_acceptance=False,
    )
    conversion_options["SVDCalcium"] = dict(
        plane_segmentation_name="SVDTemporalComponentsCalcium", **processed_data_conversion_options
    )
    conversion_options["SVDIsosbestic"] = dict(
        plane_segmentation_name="SVDTemporalComponentsIsosbestic", **processed_data_conversion_options
    )

    # Add landmarks
    if IblWidefieldLandmarksInterface.check_availability(one=one, eid=eid)["available"]:
        data_interfaces["Landmarks"] = IblWidefieldLandmarksInterface(**interface_kwargs)
        conversion_options["Landmarks"] = dict()

    # ========================================================================
    # Behavior interfaces
    # ========================================================================

    data_interfaces["BrainwideMapTrials"] = BrainwideMapTrialsInterface(**interface_kwargs)
    data_interfaces["WheelPosition"] = WheelPositionInterface(**interface_kwargs)
    data_interfaces["WheelMovements"] = WheelMovementsInterface(**interface_kwargs)
    data_interfaces["WheelKinematics"] = WheelKinematicsInterface(**interface_kwargs)

    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveIntervals"] = PassiveIntervalsInterface(**interface_kwargs)

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveReplayStim"] = PassiveReplayStimInterface(**interface_kwargs)

    if PassiveRFMInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveRFM"] = PassiveRFMInterface(**interface_kwargs)

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces["Lick"] = LickInterface(**interface_kwargs)

    camera_name_pattern = r"(leftCamera|rightCamera|bodyCamera)"
    pose_estimation_files = {Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")}
    for pose_estimation_file in pose_estimation_files:
        camera_name = re.search(pattern=camera_name_pattern, string=pose_estimation_file).group(1)
        pose_availability = IblPoseEstimationInterface.check_availability(one=one, eid=eid, camera_name=camera_name)
        if pose_availability["available"]:
            tracker = "dlc" if pose_availability.get("alternative_used") == "dlc" else "lightningPose"
            data_interfaces[f"PoseEstimation_{camera_name}"] = IblPoseEstimationInterface(
                camera_name=camera_name, tracker=tracker, **interface_kwargs
            )
        else:
            print(f"Pose estimation for '{camera_name}' not available, skipping.")

    for pupil_tracking_file in one.list_datasets(eid=eid, filename="*features*"):
        camera_name = re.search(pattern=camera_name_pattern, string=pupil_tracking_file).group(1)
        if PupilTrackingInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"PupilTracking_{camera_name}"] = PupilTrackingInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"Pupil tracking for '{camera_name}' not available, skipping.")

    for roi_motion_energy_file in one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*"):
        camera_name = re.search(pattern=camera_name_pattern, string=roi_motion_energy_file).group(1)
        if RoiMotionEnergyInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"RoiMotionEnergy_{camera_name}"] = RoiMotionEnergyInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"ROI motion energy for '{camera_name}' not available, skipping.")

    if SessionEpochsInterface.check_availability(one, eid)["available"]:
        data_interfaces["SessionEpochs"] = SessionEpochsInterface(**interface_kwargs)

    # ========================================================================
    # STEP 2: Create converter and write NWB
    # ========================================================================

    converter = WidefieldProcessedNWBConverter(one=one, session=eid, data_interfaces=data_interfaces)

    metadata = converter.get_metadata()
    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision="2025-05-06"))

    print(f"Writing to NWB '{nwbfile_path}' ...")
    conversion_start = time.time()

    converter.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

    backend_configuration = get_default_backend_configuration(nwbfile=nwbfile, backend="hdf5")
    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend_configuration=backend_configuration,
    )

    conversion_time = time.time() - conversion_start
    total_size_bytes = nwbfile_path.stat().st_size
    total_size_gb = total_size_bytes / (1024**3)

    print(f"Conversion completed in {int(conversion_time // 60)}:{conversion_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({nwbfile_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return nwbfile_path
