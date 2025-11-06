"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path

from ibl_widefield_to_nwb.widefield2025.conversion import convert_raw_session


def session_to_nwb(
    raw_data_dir_path: str | Path,
    cache_dir_path: str | Path,
    processed_data_dir_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    output_dir_path: str | Path,
    mode: str = "raw",
    force_cache: bool = False,
    stub_test: bool = False,
):
    """
    Convert a single session of widefield raw imaging data to NWB format.

    Parameters
    ----------
    raw_data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    cache_dir_path: str or Path
        Path to the directory for caching intermediate data.
    processed_data_dir_path: str or Path
        Path to the directory containing processed data.
    output_dir_path: str or Path
        Path to the directory where the output NWB file will be saved.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).

    """

    match mode:
        case "raw":
            nwbfile_path = convert_raw_session(
                raw_data_dir_path=raw_data_dir_path,
                cache_dir_path=cache_dir_path,
                processed_data_dir_path=processed_data_dir_path,
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                output_dir_path=output_dir_path,
                force_cache=force_cache,
                stub_test=stub_test,
            )


if __name__ == "__main__":

    # Parameters for conversion
    raw_data_dir_path = Path("/Users/weian/data/IBL/raw_widefield_data")
    cache_dir_path = raw_data_dir_path / "cache_test"
    processed_data_dir_path = Path("/Users/weian/data/IBL/alf/widefield")
    output_dir_path = Path("/Volumes/T9/data/IBL")

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = False  # Set to True for quick testing with limited data
    session_to_nwb(
        mode="raw",
        raw_data_dir_path=raw_data_dir_path,
        cache_dir_path=cache_dir_path,
        processed_data_dir_path=processed_data_dir_path,
        output_dir_path=output_dir_path,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
    )
