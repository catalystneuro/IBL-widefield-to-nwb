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
