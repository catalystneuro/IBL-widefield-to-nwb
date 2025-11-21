from copy import deepcopy
from pathlib import Path

from neuroconv.datainterfaces.ophys.basesegmentationextractorinterface import (
    BaseSegmentationExtractorInterface,
)
from neuroconv.utils import DeepDict, load_dict_from_file
from pydantic import DirectoryPath

from ibl_widefield_to_nwb.widefield2025.datainterfaces._ibl_widefield_segmentationextractor import (
    WidefieldSegmentationExtractor,
)


class WidefieldSegmentationInterface(BaseSegmentationExtractorInterface):
    """Data interface for IBL Widefield processed data."""

    display_name = "IBL Widefield Segmentation"
    associated_suffixes = (".npy", ".json", ".htsv")
    info = "Interface for Widefield segmentation."

    @classmethod
    def get_extractor_class(cls):
        return WidefieldSegmentationExtractor

    def __init__(
        self,
        folder_path: DirectoryPath,
        excitation_wavelength_nm: int,
        verbose: bool = False,
    ):
        """

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to the folder containing the segmentation data.
        excitation_wavelength_nm : int
            The excitation wavelength (in nm) for the channel to load.
        verbose : bool, default : False
            Whether to print verbose output.
        """
        self.verbose = verbose
        super().__init__(folder_path=folder_path, excitation_wavelength_nm=excitation_wavelength_nm)

    def get_metadata(self) -> DeepDict:
        """
        Get metadata for the Widefield segmentation.

        Returns
        -------
        DeepDict
            Dictionary containing metadata including device information, imaging plane, plane segmentation, and fluorescence
            traces metadata.
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

        imaging_plane_name = imaging_plane_metadata["name"]
        plane_segmentation_metadata = next(
            (
                plane_segmentation_meta
                for plane_segmentation_meta in ophys_metadata["Ophys"]["ImageSegmentation"]["plane_segmentations"]
                if plane_segmentation_meta.get("imaging_plane") == imaging_plane_name
            ),
            None,
        )
        if plane_segmentation_metadata is None:
            raise ValueError(f"No 'PlaneSegmentation' metadata found for imaging plane: {imaging_plane_name}. ")

        metadata_copy["Ophys"]["Device"] = ophys_metadata["Ophys"]["Device"]
        metadata_copy["Ophys"]["ImagingPlane"][0].update(imaging_plane_metadata)
        metadata_copy["Ophys"]["ImageSegmentation"]["plane_segmentations"][0].update(plane_segmentation_metadata)

        plane_segmentation_name = plane_segmentation_metadata["name"]
        metadata_copy["Ophys"]["Fluorescence"].update(
            {plane_segmentation_name: ophys_metadata["Ophys"]["Fluorescence"][plane_segmentation_name]}
        )
        metadata_copy["Ophys"]["SegmentationImages"].update(
            {plane_segmentation_name: ophys_metadata["Ophys"]["SegmentationImages"][plane_segmentation_name]}
        )
        if "Calcium" in plane_segmentation_name:
            metadata_copy["Ophys"]["DfOverF"].update(
                {plane_segmentation_name: ophys_metadata["Ophys"]["DfOverF"][plane_segmentation_name]}
            )

        return metadata_copy
