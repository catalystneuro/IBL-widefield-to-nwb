"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path


def session_to_nwb(
    data_dir_path: str | Path,
    cache_dir_path: str | Path,
    functional_channel_id: int,
    isosbestic_channel_id: int,
    output_dir_path: str | Path,
    mode: str = "raw",
    force_cache: bool = False,
    stub_test: bool = False,
):
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    cache_dir_path: str or Path
        Path to the directory for caching intermediate data.
    output_dir_path: str or Path
        Path to the directory where the output NWB file will be saved.
    functional_channel_id: int
        Channel ID for the functional (calcium) imaging data.
    isosbestic_channel_id: int
        Channel ID for the isosbestic imaging data.
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

    """

    match mode:
        case "raw":
            from ibl_widefield_to_nwb.widefield2025.conversion import (
                convert_raw_session,
            )

            nwbfile_path = convert_raw_session(
                data_dir_path=data_dir_path,
                cache_dir_path=cache_dir_path,
                functional_channel_id=functional_channel_id,
                isosbestic_channel_id=isosbestic_channel_id,
                output_dir_path=output_dir_path,
                force_cache=force_cache,
                stub_test=stub_test,
            )


if __name__ == "__main__":

    # Parameters for conversion
    data_dir_path = Path("/Users/weian/data/IBL/raw_widefield_data")
    cache_dir_path = data_dir_path / "cache_test"
    output_dir_path = Path("/Volumes/T9/data/IBL")

    functional_channel_id = 3  # The channel ID for functional (calcium) imaging
    isosbestic_channel_id = 2  # The channel ID for isosbestic imaging

    stub_test = False  # Set to True for quick testing with limited data
    session_to_nwb(
        mode="raw",
        data_dir_path=data_dir_path,
        cache_dir_path=cache_dir_path,
        output_dir_path=output_dir_path,
        functional_channel_id=functional_channel_id,
        isosbestic_channel_id=isosbestic_channel_id,
        stub_test=stub_test,
    )
