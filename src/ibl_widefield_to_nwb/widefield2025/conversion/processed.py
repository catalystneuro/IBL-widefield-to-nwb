import time
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter
from ibl_widefield_to_nwb.widefield2025.conversion import (
    get_processed_behavior_interfaces,
)
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
):
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
        The folder path where the NWB file will be saved. The final NWB file will be saved as:
        {output_path}/nwbfiles/{full|stub}/sub-{subject_id}/sub-{subject_id}_ses-{eid}_desc-processed_behavior+ophys.nwb
        Where {full|stub} depends on the 'stub_test' parameter, and {subject_id} is derived from the session metadata.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    stub_test: bool, default: False
        Whether to run a stub test (process a smaller subset of data for testing purposes).
    """

    processed_data_dir_path = Path(processed_data_dir_path)
    nwbfile_path = Path(nwbfile_path)
    nwbfile_path.parent.mkdir(parents=True, exist_ok=True)

    overwrite = False
    if nwbfile_path.exists() and not append_on_disk_nwbfile:
        overwrite = True

    data_interfaces = dict()
    conversion_options = dict()

    # Add SVD interfaces
    data_interfaces["SVDCalcium"] = WidefieldSVDInterface(
        one=one,
        session=eid,
        excitation_wavelength_nm=functional_wavelength_nm,
    )
    data_interfaces["SVDIsosbestic"] = WidefieldSVDInterface(
        one=one,
        session=eid,
        excitation_wavelength_nm=isosbestic_wavelength_nm,
    )

    processed_data_conversion_options = dict(
        stub_test=stub_test,
        include_roi_centroids=False,
        include_roi_acceptance=False,
    )
    conversion_options.update(
        dict(
            SVDCalcium=dict(plane_segmentation_name="SVDTemporalComponentsCalcium", **processed_data_conversion_options)
        )
    )
    conversion_options.update(
        dict(
            SVDIsosbestic=dict(
                plane_segmentation_name="SVDTemporalComponentsIsosbestic", **processed_data_conversion_options
            )
        )
    )

    # Add landmarks
    if IblWidefieldLandmarksInterface.check_availability(one=one, eid=eid)["available"]:
        data_interfaces["Landmarks"] = IblWidefieldLandmarksInterface(one=one, session=eid)
        conversion_options.update(dict(Landmarks=dict()))

    # Add Behavior
    behavior_interfaces = get_processed_behavior_interfaces(one=one, eid=eid)
    data_interfaces.update(behavior_interfaces)

    converter = WidefieldProcessedNWBConverter(one=one, session=eid, data_interfaces=data_interfaces)

    # Add datetime to conversion
    metadata = converter.get_metadata()
    session_start_time = metadata["NWBFile"]["session_start_time"]
    if session_start_time.tzinfo is None:
        session_start_time = session_start_time.replace(tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = session_start_time

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent.parent / "_metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    print(f"Writing to NWB '{nwbfile_path}' ...")
    conversion_start = time.time()

    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        append_on_disk_nwbfile=append_on_disk_nwbfile,
        overwrite=overwrite,
    )

    conversion_time = time.time() - conversion_start

    # Calculate total size
    total_size_bytes = nwbfile_path.stat().st_size
    total_size_gb = total_size_bytes / (1024**3)

    print(f"Conversion completed in {int(conversion_time // 60)}:{conversion_time % 60:05.2f} (MM:SS.ss)")
    print(f"Total data ({nwbfile_path.name}) size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return nwbfile_path
