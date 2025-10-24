from copy import deepcopy

import numpy as np
from neuroconv.datainterfaces.ophys.basesegmentationextractorinterface import (
    BaseSegmentationExtractorInterface,
)
from neuroconv.utils import DeepDict
from pydantic import DirectoryPath

from src.ibl_widefield_to_nwb.widefield2025.ibl_widefield_segmentationextractor import (
    WidefieldSegmentationExtractor,
)


class WidefieldSegmentationInterface(BaseSegmentationExtractorInterface):
    """Data interface for IBL Widefield processed data."""

    display_name = "IBL Widefield Segmentation"
    associated_suffixes = (".npy", ".json", ".htsv")
    info = "Interface for Widefield segmentation."

    Extractor = WidefieldSegmentationExtractor

    def __init__(
        self,
        folder_path: DirectoryPath,
        channel_id: int | None = None,
        verbose: bool = False,
    ):
        """

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to the folder containing the segmentation data.
        channel_id : int, optional
            Specific channel ID to extract. If None, all channels are extracted.
        verbose : bool, default : False
            Whether to print verbose output.
        """
        self.verbose = verbose
        super().__init__(folder_path=folder_path, channel_id=channel_id)

    def get_metadata(self) -> DeepDict:
        """Return metadata for this segmentation extractor."""
        metadata = super().get_metadata()
        metadata_copy = deepcopy(metadata)  # To avoid modifying the parent class's metadata
        imaging_plane_metadata = metadata_copy["Ophys"]["ImagingPlane"][0]
        imaging_light_source_properties = self.segmentation_extractor.get_imaging_light_source_properties()

        color = imaging_light_source_properties["color"]
        excitation_wavelength = float(imaging_light_source_properties["wavelength"])
        suffix = "calcium" if excitation_wavelength == 470.0 else "isosbestic"
        imaging_plane_metadata.update(
            name=f"imaging_plane_{suffix}",
            description=f"The imaging plane for calcium imaging from {color} channel.",
            excitation_lambda=excitation_wavelength,
        )
        optical_channel_metadata = imaging_plane_metadata["optical_channel"][0]
        # Additional metadata would be loaded from yaml
        emission_lambda = np.nan  # Placeholder for now
        optical_channel_metadata.update(
            description="Optical channel for calcium imaging",
            emission_lambda=emission_lambda,
        )

        image_segmentation_metadata = metadata_copy["Ophys"]["ImageSegmentation"]
        plane_segmentations_metadata = image_segmentation_metadata["plane_segmentations"][0]
        plane_segmentation_name = f"plane_segmentation_{suffix}"
        plane_segmentations_metadata.update(
            name=plane_segmentation_name,
            imaging_plane=imaging_plane_metadata["name"],
            description=f"Segmentation for widefield calcium imaging from {color} channel.",
        )

        fluorescence_metadata = metadata_copy["Ophys"]["Fluorescence"]
        default_roi_response_raw_metadata = fluorescence_metadata["PlaneSegmentation"]
        default_roi_response_raw_metadata["raw"].update(
            name=f"roi_response_series_{suffix}",
            description=f"Raw fluorescence traces for widefield calcium imaging from {color} channel.",
        )
        fluorescence_metadata.update({plane_segmentation_name: default_roi_response_raw_metadata})

        # Only update for functional channel
        if excitation_wavelength == 470.0:
            dff_metadata = metadata_copy["Ophys"]["DfOverF"]
            default_roi_response_dff_metadata = dff_metadata["PlaneSegmentation"]
            default_roi_response_dff_metadata["dff"].update(
                name=f"roi_response_series_{suffix}",
                description=f"Df/F traces for widefield calcium imaging from {color} channel.",
            )
            dff_metadata.update({plane_segmentation_name: default_roi_response_dff_metadata})

        segmentation_images_metadata = metadata_copy["Ophys"]["SegmentationImages"]
        default_image_masks_metadata = segmentation_images_metadata["PlaneSegmentation"]
        default_image_masks_metadata.update(
            mean=dict(
                name=f"mean_{suffix}",
                description=f"Mean image for widefield calcium imaging from {color} channel.",
            )
        )
        segmentation_images_metadata.update({plane_segmentation_name: default_image_masks_metadata})

        return metadata_copy
