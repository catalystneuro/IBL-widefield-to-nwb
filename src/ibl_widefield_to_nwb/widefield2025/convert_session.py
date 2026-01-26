"""Primary script to run to convert an entire session for of data using the NWBConverter."""

from pathlib import Path

from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.conversion import (
    convert_processed_session,
    convert_raw_session,
    download_widefield_session,
)


def session_to_nwb(
    one: ONE,
    eid: str,
    nwb_folder_path: str | Path,
    functional_wavelength_nm: int,
    isosbestic_wavelength_nm: int,
    mode: str = "raw",
    force_cache: bool = False,
    stub_test: bool = False,
    append_on_disk_nwbfile: bool = False,
    redownload_data: bool = False,
):
    """
    Convert a single session of widefield data to NWB format.

    Parameters
    ----------
    one: ONE
        An instance of the ONE API to access data.
    eid: str
        The session ID.
    nwb_folder_path: str or Path
        Path to the directory to save the output NWB file.
    raw_data_dir_path: str or Path
        Path to the directory containing the raw widefield data for the session.
    cache_dir_path: str or Path
        Path to the directory for caching intermediate data.
    nidq_data_dir_path: str or Path
        Path to the directory containing NIDQ data.
    processed_data_dir_path: str or Path
        Path to the directory containing processed widefield data.
    functional_wavelength_nm: int
        Wavelength (in nm) for the functional imaging data.
    isosbestic_wavelength_nm: int
        Wavelength (in nm) for the isosbestic imaging data.
    mode: str, default: "raw"
        Mode of conversion. Options are "raw" or "processed".
    force_cache: bool, default: False
        If True, force rebuilding of the cache even if it already exists.
    stub_test: bool, default: False
        If True, run a stub test (process a small subset of the data for testing purposes).
    append_on_disk_nwbfile: bool, default: False
        If True, append data to an existing on-disk NWB file instead of creating a new one.
    redownload_data: bool, default: False
        If True, redownload data from ONE even if it already exists locally.
    """

    nwb_folder_path = Path(nwb_folder_path)
    nwb_folder_path.mkdir(parents=True, exist_ok=True)

    try:
        ((session_metadata),) = one.alyx.rest(url="sessions", action="list", id=eid)
    except Exception as e:
        raise RuntimeError(f"Failed to access ONE for eid {eid}: {e}")

    subject_id = session_metadata["subject"]
    nwbfile_path = Path(nwb_folder_path) / f"sub-{subject_id}_ses-{eid}_desc-{mode}_ophys+behavior.nwb"

    one_api_kwargs = dict(one=one, eid=eid)

    # ========================================================================
    # STEP 1: Download Widefield Session Data
    # ========================================================================

    downloaded_file_paths = download_widefield_session(
        eid=eid,
        one=one,
        mode=mode,
        redownload_data=redownload_data,
    )

    # Organize downloaded files by collection
    widefield_session = {}
    for file_path in downloaded_file_paths:
        widefield_session[file_path.collection] = Path(file_path.parent)

    # ========================================================================
    # STEP 2: Convert Widefield Session Data to NWB
    # ========================================================================

    match mode:
        case "raw":
            one_api_kwargs.update(
                subject_id=subject_id,
                nwbfiles_folder_path=nwb_folder_path,
            )

            nwbfile_path = convert_raw_session(
                nwbfile_path=nwbfile_path,
                raw_data_dir_path=widefield_session["raw_widefield_data"],
                cache_dir_path=widefield_session["raw_widefield_data"] / "wf_cache",
                nidq_data_dir_path=widefield_session["raw_ephys_data"],
                processed_data_dir_path=widefield_session["alf/widefield"],
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                one_api_kwargs=one_api_kwargs,
                force_cache=force_cache,
                stub_test=stub_test,
                append_on_disk_nwbfile=append_on_disk_nwbfile,
            )
        case "processed":
            nwbfile_path = convert_processed_session(
                nwbfile_path=nwbfile_path,
                processed_data_dir_path=widefield_session["alf/widefield"],
                functional_wavelength_nm=functional_wavelength_nm,
                isosbestic_wavelength_nm=isosbestic_wavelength_nm,
                one_api_kwargs=one_api_kwargs,
                stub_test=stub_test,
                append_on_disk_nwbfile=append_on_disk_nwbfile,
            )

    print(f"\n✓ NWB file created/updated successfully at: {nwbfile_path}")


if __name__ == "__main__":

    # Parameters for conversion
    output_dir_path = Path("/Volumes/T9/data/IBL/nwbfiles")
    append_on_disk_nwbfile = False  # Set to True to append to an existing NWB file

    functional_wavelength_nm = 470  # The wavelength for functional imaging (e.g. 470 nm)
    isosbestic_wavelength_nm = 405  # The wavelength for isosbestic imaging (e.g. 405 nm)

    stub_test = True  # Set to True for quick testing with limited data

    # ONE api instance
    from one.api import ONE

    one = ONE()
    # eid = "d34a502f-bd06-471f-8334-df41f785e1d9" error 404 for raw data
    eid = "2864dca1-38d8-464c-9777-f6fdfd5e63b5"

    mode = "processed"  # Choose between "raw" or "processed" mode

    session_to_nwb(
        one=one,
        eid=eid,
        nwb_folder_path=output_dir_path,
        mode=mode,
        functional_wavelength_nm=functional_wavelength_nm,
        isosbestic_wavelength_nm=isosbestic_wavelength_nm,
        stub_test=stub_test,
        append_on_disk_nwbfile=append_on_disk_nwbfile,
    )
