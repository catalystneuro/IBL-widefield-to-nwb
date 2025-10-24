"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldProcessedNWBConverter


def processed_imaging_session_to_nwb(
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    functional_channel_id: int,
    isosbestic_channel_id: int,
    stub_test: bool = False,
):
    """
    Convert a single session of processed widefield imaging data to NWB format.

    Expected file structure:
    data_dir_path/
      ├── imaging.imagingLightSource.afbbadcd-be70-410b-becf-db547c6a9d78.npy
      ├── imaging.times.9f634c9e-33ba-4386-993a-e386fe909397.npy
      ├── imagingLightSource.properties.3e8acb33-0cee-4ba9-8ad4-5b305b74fee0.htsv
      ├── widefieldChannels.frameAverage.4b030254-be6d-4e8a-bf40-8316df71b710.npy
      ├── widefieldSVT.haemoCorrected.fb72c7a7-6165-4931-9d6e-3600b26ea525.npy
      ├── widefieldSVT.uncorrected.54b4c57c-b25c-4eb9-9d0f-76654d84a005.npy
      └── widefieldU.images.75628fe6-1c05-4a62-96c9-0478ebfa42b0.npy

    Parameters
    ----------
    data_dir_path: str | Path
        Path to the directory containing the processed widefield imaging data.
    output_dir_path: str | Path
        Path to the directory where the NWB file will be saved.
    functional_channel_id: int
        The channel ID for the functional (e.g., calcium) imaging data.
    isosbestic_channel_id: int
        The channel ID for the isosbestic imaging data.
    stub_test: bool, default: False
        Whether to run a stub test (process a smaller subset of data for testing purposes).

    """

    data_dir_path = Path(data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    session_id = "subject_identifier_usually"
    nwbfile_path = output_dir_path / f"{session_id}.nwb"

    source_data = dict()
    conversion_options = dict()

    # Add Segmentation
    source_data.update(dict(SegmentationBlue=dict(folder_path=data_dir_path, channel_id=functional_channel_id)))
    conversion_options.update(
        dict(SegmentationBlue=dict(plane_segmentation_name="plane_segmentation_calcium", stub_test=stub_test))
    )
    source_data.update(dict(SegmentationViolet=dict(folder_path=data_dir_path, channel_id=isosbestic_channel_id)))
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
    data_dir_path = Path("/Users/weian/data/IBL")
    output_dir_path = Path("/Users/weian/data/IBL/nwbfiles")

    functional_channel_id = 2  # channel ID for functional imaging
    isosbestic_channel_id = 1  # channel ID for isosbestic imaging
    stub_test = True
    processed_imaging_session_to_nwb(
        data_dir_path=data_dir_path,
        output_dir_path=output_dir_path,
        functional_channel_id=functional_channel_id,
        isosbestic_channel_id=isosbestic_channel_id,
        stub_test=stub_test,
    )
