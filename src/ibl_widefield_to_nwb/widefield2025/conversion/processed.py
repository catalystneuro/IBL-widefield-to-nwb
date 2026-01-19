import time
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter
from ibl_widefield_to_nwb.widefield2025.conversion import (
    get_processed_behavior_interfaces,
)
from ibl_widefield_to_nwb.widefield2025.datainterfaces import WidefieldSVDInterface


def convert_processed_session(
    nwbfile_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    one_api_kwargs: dict,
    stub_test: bool = False,
    append_on_disk_nwbfile: bool = False,
):
    """
    Convert a single session of processed widefield imaging data to NWB format.

    Expected file structure:
    data_dir_path/
      ├── imaging.imagingLightSource.npy
      ├── imaging.times.npy
      ├── imagingLightSource.properties.htsv
      ├── widefieldChannels.frameAverage.npy
      ├── widefieldSVT.haemoCorrected.npy
      ├── widefieldSVT.uncorrected.npy
      └── widefieldU.images.npy

    Parameters
    ----------
    nwbfile_path: str | Path
        Path to the output NWB file.
    processed_data_dir_path: str | Path
        Path to the directory containing the processed widefield imaging data.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    one_api_kwargs: dict
        Keyword arguments to initialize the interfaces that require ONE API access.
    stub_test: bool, default: False
        Whether to run a stub test (process a smaller subset of data for testing purposes).
    append_on_disk_nwbfile: bool, default: False
        If True, append data to an existing on-disk NWB file instead of creating a new one.
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
        folder_path=processed_data_dir_path,
        excitation_wavelength_nm=functional_wavelength_nm,
    )
    data_interfaces["SVDIsosbestic"] = WidefieldSVDInterface(
        folder_path=processed_data_dir_path,
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
    landmarks_file_path = processed_data_dir_path / "widefieldLandmarks.dorsalCortex.json"
    if landmarks_file_path.exists():
        source_data.update(dict(Landmarks=dict(file_path=landmarks_file_path)))
        conversion_options.update(dict(Landmarks=dict()))

    # Add Behavior
    behavior_interfaces = get_processed_behavior_interfaces(**one_api_kwargs)
    data_interfaces.update(behavior_interfaces)

    converter = WidefieldProcessedNWBConverter(**one_api_kwargs, data_interfaces=data_interfaces)

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
