"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter


def processed_imaging_session_to_nwb(
    processed_data_dir_path: str | Path,
    output_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    stub_test: bool = False,
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
    processed_data_dir_path: str | Path
        Path to the directory containing the processed widefield imaging data.
    output_dir_path: str | Path
        Path to the directory where the NWB file will be saved.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    stub_test: bool, default: False
        Whether to run a stub test (process a smaller subset of data for testing purposes).

    """

    processed_data_dir_path = Path(processed_data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    session_id = "subject_identifier_usually"
    nwbfile_path = output_dir_path / f"{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # Add Segmentation
    source_data.update(
        dict(
            SegmentationBlue=dict(
                folder_path=processed_data_dir_path, excitation_wavelength_nm=functional_wavelength_nm
            )
        )
    )
    conversion_options.update(
        dict(SegmentationBlue=dict(plane_segmentation_name="plane_segmentation_calcium", stub_test=stub_test))
    )
    source_data.update(
        dict(
            SegmentationViolet=dict(
                folder_path=processed_data_dir_path, excitation_wavelength_nm=isosbestic_wavelength_nm
            )
        )
    )
    conversion_options.update(
        dict(SegmentationViolet=dict(plane_segmentation_name="plane_segmentation_isosbestic", stub_test=stub_test))
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
    editable_metadata_path = Path(__file__).parent / "metadata" / "widefield_general_metadata.yaml"
    editable_metadata = load_dict_from_file(editable_metadata_path)
    metadata = dict_deep_update(metadata, editable_metadata)

    # Update ophys metadata
    ophys_metadata_path = Path(__file__).parent / "metadata" / "widefield_ophys_metadata.yaml"
    ophys_metadata = load_dict_from_file(ophys_metadata_path)
    metadata = dict_deep_update(metadata, ophys_metadata)

    metadata["Subject"]["subject_id"] = "a_subject_id"  # Modify here or in the yaml file

    # Run conversion
    converter.run_conversion(
        metadata=metadata,
        nwbfile_path=nwbfile_path,
        conversion_options=conversion_options,
        overwrite=True,
    )


if __name__ == "__main__":

    # Parameters for conversion
    processed_data_dir_path = Path("/Users/weian/data/IBL/alf/widefield")
    output_dir_path = Path("/Users/weian/data/IBL/nwbfiles")

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = True
    processed_imaging_session_to_nwb(
        processed_data_dir_path=processed_data_dir_path,
        output_dir_path=output_dir_path,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
    )
