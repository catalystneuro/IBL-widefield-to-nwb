from copy import deepcopy
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from neuroconv.datainterfaces.ophys.baseimagingextractorinterface import (
    BaseImagingExtractorInterface,
)
from neuroconv.utils import DeepDict, dict_deep_update, load_dict_from_file
from one.api import ONE
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.datainterfaces._base_ibl_interface import (
    BaseIBLDataInterface,
)
from ibl_widefield_to_nwb.widefield2025.datainterfaces._ibl_widefield_imagingextractor import (
    TRANSPOSE_OUTPUT,
    WidefieldImagingExtractor,
)


class WidefieldImagingInterface(BaseImagingExtractorInterface, BaseIBLDataInterface):
    """Data Interface for WidefieldImagingExtractor."""

    display_name = "IBL Widefield Imaging"
    associated_suffixes = (".mov", ".htsv", ".camlog")
    info = "Interface for IBL Widefield imaging data."

    @classmethod
    def get_extractor_class(cls):
        return WidefieldImagingExtractor

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for raw Widefield data.

        Returns
        -------
        dict
            Data requirements specification with exact file paths
        """
        return {
            "one_objects": [],  # Uses load_dataset directly, not load_object
            "exact_files_options": {
                "standard": [
                    "raw_widefield_data/imaging.frames.mov",
                    "raw_widefield_data/widefieldChannels.wiring.htsv",
                    "raw_widefield_data/widefieldEvents.raw.camlog",
                    # For aligned timestamps
                    "alf/widefield/imaging.times.npy",
                    "alf/widefield/imaging.imagingLightSource.npy",
                    "alf/widefield/imagingLightSource.properties.htsv",
                ]
            },
        }

    def __init__(
        self,
        one: ONE,
        session: str,
        cache_folder_path: DirectoryPath,
        excitation_wavelength_nm: int | None = None,
        photon_series_type: Literal["OnePhotonSeries", "TwoPhotonSeries"] = "OnePhotonSeries",
        verbose: bool = False,
    ):
        """
        Parameters
        ----------
        one : ONE
            The ONE API instance for data access.
        session : str
            The session ID (eid).
        cache_folder_path : DirectoryPath
            Path to the frame-cache folder produced by build_frame_cache (contains frames.dat and meta.json).
        excitation_wavelength_nm : int, optional
            Excitation wavelength in nm (e.g. 470 for calcium, 405 for isosbestic).
        photon_series_type : str, default "OnePhotonSeries"
            NWB photon series type.
        verbose : bool, default False
            Whether to print verbose output.
        """
        super().__init__(
            one=one,
            session=session,
            cache_folder_path=cache_folder_path,
            excitation_wavelength_nm=excitation_wavelength_nm,
            photon_series_type=photon_series_type,
            verbose=verbose,
        )

    def get_metadata(self) -> DeepDict:
        """
        Get metadata for the Widefield raw imaging.

        Returns
        -------
        DeepDict
            Dictionary containing metadata including device information, imaging plane details,
            and one-photon series configuration.
        """
        metadata = super().get_metadata()
        metadata_copy = deepcopy(metadata)

        # Use single source of truth when updating metadata
        ophys_metadata = load_dict_from_file(
            file_path=Path(__file__).parent.parent / "_metadata" / "widefield_ophys_metadata.yaml"
        )

        excitation_wavelength = float(self.source_data["excitation_wavelength_nm"])
        imaging_plane_metadata = next(
            (
                imaging_plane_meta
                for imaging_plane_meta in ophys_metadata["Ophys"]["ImagingPlane"]
                if imaging_plane_meta.get("excitation_lambda") == excitation_wavelength
            ),
            None,
        )
        if imaging_plane_metadata is None:
            raise ValueError(
                f"No 'ImagingPlane' metadata found for excitation wavelength: {excitation_wavelength} nm. "
            )
        imaging_plane_metadata.update(
            imaging_rate=float(self.imaging_extractor.get_sampling_frequency()),
        )
        imaging_plane_name = imaging_plane_metadata["name"]
        one_photon_series_metadata = next(
            (
                photon_series_meta
                for photon_series_meta in ophys_metadata["Ophys"]["OnePhotonSeries"]
                if photon_series_meta.get("imaging_plane") == imaging_plane_name
            ),
            None,
        )
        if one_photon_series_metadata is None:
            raise ValueError(f"No 'OnePhotonSeries' metadata found for imaging plane: {imaging_plane_name}. ")

        # TODO: remove once neuroconv supports (height, width) format
        if TRANSPOSE_OUTPUT:
            # Transpose it back to height x width (now it matches the series shape)
            one_photon_series_metadata["dimension"] = self.imaging_extractor.get_sample_shape()[::-1]

        metadata_copy["Ophys"]["Device"] = ophys_metadata["Ophys"]["Device"]
        metadata_copy["Ophys"]["ImagingPlane"][0] = dict_deep_update(
            metadata_copy["Ophys"]["ImagingPlane"][0], imaging_plane_metadata
        )
        metadata_copy["Ophys"]["OnePhotonSeries"][0] = dict_deep_update(
            metadata_copy["Ophys"]["OnePhotonSeries"][0], one_photon_series_metadata
        )

        return metadata_copy

    def get_aligned_timestamps(self) -> np.ndarray:
        """
        Return aligned imaging timestamps for this interface's excitation wavelength.

        Loads the aligned ``imaging.times`` and ``imaging.imagingLightSource`` arrays from
        the ONE API and filters them to the wavelength set on this interface.

        Returns
        -------
        np.ndarray
            1-D array of timestamps (seconds) for the selected excitation wavelength.
        """
        one = self.imaging_extractor.one
        session = self.imaging_extractor.session
        excitation_wavelength_nm = self.imaging_extractor.excitation_wavelength_nm

        collection = "alf/widefield"
        all_times = one.load_dataset(session, "imaging.times", collection=collection)
        light_sources = one.load_dataset(session, "imaging.imagingLightSource", collection=collection)

        # Resolve channel_id for this wavelength; fall back to direct CSV read if ONE misparses the htsv
        light_source_props = one.load_dataset(session, "imagingLightSource.properties", collection=collection)
        if "wavelength" not in light_source_props:
            session_path = one.eid2path(session)
            htsv_path = session_path / collection / "imagingLightSource.properties.htsv"
            light_source_props = pd.read_csv(htsv_path, sep=None, engine="python")

        channel_ids = light_source_props.loc[
            light_source_props["wavelength"] == excitation_wavelength_nm, "channel_id"
        ].tolist()
        if not channel_ids:
            raise ValueError(f"No channel ID found for wavelength {excitation_wavelength_nm} nm.")
        channel_id = channel_ids[0]

        n_samples = min(len(all_times), len(light_sources))
        times_per_channel = all_times[:n_samples][light_sources[:n_samples] == channel_id]
        return times_per_channel
