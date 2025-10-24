"""Primary script to run to convert an entire session for of data using the NWBConverter."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_widefield_to_nwb.widefield2025 import WidefieldRawNWBConverter


def raw_imaging_session_to_nwb(
    data_dir_path: str | Path,
    functional_channel_id: int,
    isosbestic_channel_id: int,
    output_dir_path: str | Path,
    stub_test: bool = False,
):
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    output_dir_path: str or Path
        Path to the directory where the output NWB file will be saved.
    functional_channel_id: int
        Channel ID for the functional (calcium) imaging data.
    isosbestic_channel_id: int
        Channel ID for the isosbestic imaging data.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

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

    # Add Imaging
    source_data.update(dict(ImagingBlue=dict(folder_path=data_dir_path, channel_id=functional_channel_id)))
    conversion_options.update(
        dict(
            ImagingBlue=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=0,
                stub_test=stub_test,
                iterator_options=dict(display_progress=True),
            )
        )
    )
    source_data.update(dict(ImagingViolet=dict(folder_path=data_dir_path, channel_id=isosbestic_channel_id)))
    conversion_options.update(
        dict(
            ImagingViolet=dict(
                photon_series_type="OnePhotonSeries",
                photon_series_index=1,
                stub_test=stub_test,
                iterator_options=dict(display_progress=True),
            )
        )
    )

    # Add Behavior
    # source_data.update(dict(Behavior=dict()))
    # conversion_options.update(dict(Behavior=dict()))

    converter = WidefieldRawNWBConverter(source_data=source_data)

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
    converter.run_conversion(metadata=metadata, nwbfile_path=nwbfile_path, conversion_options=conversion_options)


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Users/weian/data/IBL/raw_widefield_data")
    output_dir_path = Path("/Volumes/T9/data/IBL")

    functional_channel_id = 3  # The channel ID for functional (calcium) imaging
    isosbestic_channel_id = 2  # The channel ID for isosbestic imaging

    stub_test = True
    raw_imaging_session_to_nwb(
        data_dir_path=data_dir_path,
        output_dir_path=output_dir_path,
        functional_channel_id=functional_channel_id,
        isosbestic_channel_id=isosbestic_channel_id,
        stub_test=stub_test,
    )
