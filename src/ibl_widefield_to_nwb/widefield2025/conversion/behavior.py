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
    except ImportError as e:
        raise ImportError(
            "ibl_to_nwb is required for processed behavior conversion. "
            # TODO update URL
            "Please install it from https://github.com/h-mayorquin/IBL-to-nwb/blob/heberto_conversion."
        ) from e

    data_interfaces = dict()
    interface_kwargs = dict(one=one, session=eid)

    data_interfaces["BrainwideMapTrials"] = BrainwideMapTrialsInterface(**interface_kwargs)
    data_interfaces["WheelPosition"] = WheelPositionInterface(**interface_kwargs)
    data_interfaces["WheelMovements"] = WheelMovementsInterface(**interface_kwargs)
    data_interfaces["WheelKinematics"] = WheelKinematicsInterface(**interface_kwargs)

    # Passive period data - add each interface if its data is available
    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveIntervals"] = PassiveIntervalsInterface(**interface_kwargs)

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveReplayStim"] = PassiveReplayStimInterface(**interface_kwargs)

    if PassiveRFMInterface.check_availability(one, eid)["available"]:
        data_interfaces["PassiveRFM"] = PassiveRFMInterface(**interface_kwargs)

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces["Lick"] = LickInterface(**interface_kwargs)

    camera_name_pattern = r"(leftCamera|rightCamera|bodyCamera)"
    pose_estimation_files = set([Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")])
    for pose_estimation_file in pose_estimation_files:
        camera_name = re.search(pattern=camera_name_pattern, string=pose_estimation_file).group(1)
        pose_estimation_availability = IblPoseEstimationInterface.check_availability(
            one=one, eid=eid, camera_name=camera_name
        )
        if pose_estimation_availability["available"]:
            tracker = "lightningPose"
            if pose_estimation_availability["alternative_used"] == "dlc":
                tracker = "dlc"
            data_interfaces[f"PoseEstimation_{camera_name}"] = IblPoseEstimationInterface(
                camera_name=camera_name, tracker=tracker, **interface_kwargs
            )
        else:
            print(f"Pose estimation data for camera '{camera_name}' not available or failed to load, skipping...")

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    for pupil_tracking_file in pupil_tracking_files:
        camera_name = re.search(pattern=camera_name_pattern, string=pupil_tracking_file).group(1)
        if PupilTrackingInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"PupilTracking_{camera_name}"] = PupilTrackingInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"Pupil tracking data for camera '{camera_name}' not available or failed to load, skipping...")

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = re.search(pattern=camera_name_pattern, string=roi_motion_energy_file).group(1)
        if RoiMotionEnergyInterface.check_availability(one=one, eid=eid, camera_name=camera_name)["available"]:
            data_interfaces[f"RoiMotionEnergy_{camera_name}"] = RoiMotionEnergyInterface(
                camera_name=camera_name, **interface_kwargs
            )
        else:
            print(f"ROI motion energy data for camera '{camera_name}' not available or failed to load, skipping...")

    # Session epochs (high-level task vs passive phases)
    if SessionEpochsInterface.check_availability(one, eid)["available"]:
        data_interfaces["SessionEpochs"] = SessionEpochsInterface(one=one, session=eid)

    return data_interfaces
