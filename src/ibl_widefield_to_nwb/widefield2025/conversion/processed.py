import datetime
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter


def convert_processed_session(
    nwbfile_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
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

    session_id = "subject_identifier_usually"

    source_data = dict()
    conversion_options = dict()

    # Add Segmentation
    source_data.update(
        dict(
            SegmentationCalcium=dict(
                folder_path=processed_data_dir_path, excitation_wavelength_nm=functional_wavelength_nm
            )
        )
    )
    conversion_options.update(
        dict(SegmentationCalcium=dict(plane_segmentation_name="plane_segmentation_calcium", stub_test=stub_test))
    )
    source_data.update(
        dict(
            SegmentationIsosbestic=dict(
                folder_path=processed_data_dir_path, excitation_wavelength_nm=isosbestic_wavelength_nm
            )
        )
    )
    conversion_options.update(
        dict(SegmentationIsosbestic=dict(plane_segmentation_name="plane_segmentation_isosbestic", stub_test=stub_test))
    )

    # Add Behavior
    # source_data.update(dict(Behavior=dict()))
    # conversion_options.update(dict(Behavior=dict()))

    converter = WidefieldProcessedNWBConverter(source_data=source_data)

    # Add datetime to conversion
    metadata = converter.get_metadata()
    date = datetime.datetime(year=2020, month=1, day=1, tzinfo=ZoneInfo("US/Eastern"))
    metadata["NWBFile"]["session_start_time"] = date

    # Update default metadata with the editable in the corresponding yaml file
    editable_metadata_path = Path(__file__).parent.parent / "metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update ophys metadata
    ophys_metadata_path = Path(__file__).parent.parent / "metadata" / "widefield_ophys_metadata.yaml"
    ophys_metadata = load_dict_from_file(ophys_metadata_path)
    metadata = dict_deep_update(metadata, ophys_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file
    metadata["NWBFile"]["session_id"] = session_id

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
