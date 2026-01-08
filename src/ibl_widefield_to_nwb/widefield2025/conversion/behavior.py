import re
from pathlib import Path

from one.api import ONE


def get_processed_behavior_interfaces(
    one: ONE,
    eid: str,
) -> dict:
    """
    Returns a dictionary of data interfaces for processed behavior data for a given session.

    Parameters
    ----------
    one: ONE
        An instance of the ONE API to access data.
    eid: str
        The session ID.

    Returns
    -------
    dict
        A dictionary where keys are interface names and values are corresponding data interface instances.
    """

    try:
        from ibl_to_nwb.bwm_to_nwb import get_camera_name_from_file
        from ibl_to_nwb.datainterfaces import (
            BrainwideMapTrialsInterface,
            IblPoseEstimationInterface,  # not working, need to investigate
            LickInterface,
            PassiveIntervalsInterface,
            PassiveReplayStimInterface,
            PassiveRFMInterface,
            PupilTrackingInterface,
            RoiMotionEnergyInterface,
            WheelInterface,
        )
    except ImportError as e:
        raise ImportError(
            "ibl_to_nwb is required for processed behavior conversion. "
            # TODO update URL
            "Please install it from https://github.com/h-mayorquin/IBL-to-nwb/blob/heberto_conversion."
        ) from e

    data_interfaces = dict()
    interface_kwargs = dict(one=one, session=eid)

    data_interfaces["BrainwideMapTrials"] = BrainwideMapTrialsInterface(**interface_kwargs)
    data_interfaces["Wheel"] = WheelInterface(**interface_kwargs)

    # Passive period data - add each interface if its data is available
    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveIntervals"] = PassiveIntervalsInterface(**interface_kwargs)

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveReplayStim"] = PassiveReplayStimInterface(**interface_kwargs)

    if PassiveRFMInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveRFM"] = PassiveRFMInterface(**interface_kwargs)

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces["Lick"] = LickInterface(**interface_kwargs)

    pose_estimation_files = set([Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")])
    for pose_estimation_file in pose_estimation_files:
        camera_name = get_camera_name_from_file(pose_estimation_file)
        if IblPoseEstimationInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"PoseEstimation_{camera_name}"] = IblPoseEstimationInterface(
                camera_name=camera_name, tracker="lightningPose", **interface_kwargs
            )
        else:
            print(f"Pose estimation data for camera '{camera_name}' not available or failed to load, skipping...")

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    for pupil_tracking_file in pupil_tracking_files:
        camera_name = get_camera_name_from_file(pupil_tracking_file)
        if PupilTrackingInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"PupilTracking_{camera_name}"] = PupilTrackingInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"Pupil tracking data for camera '{camera_name}' not available or failed to load, skipping...")

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = get_camera_name_from_file(roi_motion_energy_file)
        if RoiMotionEnergyInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"RoiMotionEnergy_{camera_name}"] = RoiMotionEnergyInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"ROI motion energy data for camera '{camera_name}' not available or failed to load, skipping...")
    return data_interfaces


def get_raw_behavior_interfaces(
    one: ONE,
    eid: str,
    nwbfiles_folder_path: str | Path,
    subject_id: str,
) -> dict:
    """
    Returns a dictionary of data interfaces for raw behavior data for a given session.

    Parameters
    ----------

    one: ONE
        An instance of the ONE API to access data.
    eid: str
        The session ID.
    nwbfiles_folder_path: str or Path
        Path to the directory to save the output NWB file.
    subject_id: str
        The subject ID.

    Returns
    -------
    dict
        A dictionary where keys are interface names and values are corresponding data interface instances.
    """

    try:
        from ibl_to_nwb.bwm_to_nwb import get_camera_name_from_file
        from ibl_to_nwb.datainterfaces import RawVideoInterface
    except ImportError as e:
        raise ImportError(
            "ibl_to_nwb is required for processed behavior conversion. "
            # TODO update URL
            "Please install it from https://github.com/h-mayorquin/IBL-to-nwb/blob/heberto_conversion."
        ) from e

    data_interfaces = dict()
    interface_kwargs = dict(
        one=one,
        session=eid,
        subject_id=subject_id,
        nwbfiles_folder_path=nwbfiles_folder_path,
    )

    camera_files = one.list_datasets(eid, filename="*Camera.raw.mp4*")
    for camera_file in camera_files:
        camera_name = get_camera_name_from_file(camera_file)
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)
        if camera_view is None:
            raise ValueError(f"Unexpected camera name '{camera_name}' extracted from file '{camera_file}'")
        if RawVideoInterface.check_availability(one=one, eid=eid, camera_name=camera_view)["available"]:
            data_interfaces[f"RawVideo_{camera_name}"] = RawVideoInterface(camera_name=camera_view, **interface_kwargs)
        else:
            print(f"Raw video data for camera '{camera_name}' not available or failed to load, skipping...")

    return data_interfaces
