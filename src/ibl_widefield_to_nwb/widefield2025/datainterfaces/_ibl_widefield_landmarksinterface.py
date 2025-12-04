import json

from neuroconv import BaseDataInterface
from neuroconv.tools import get_module
from pydantic import FilePath
from pynwb import NWBFile
from pynwb.base import Images
from pynwb.image import GrayscaleImage
from wfield import im_apply_transform


class IBLWidefieldLandmarksInterface(BaseDataInterface):
    """Data Interface for storing landmarks from Widefield sessions in NWB."""

    interface_name = "IBLWidefieldLandmarksInterface"

    def __init__(self, file_path: FilePath):
        """
        Initialize the IBLWidefieldLandmarksInterface.

        Parameters
        ----------
        file_path: FilePath
            Path to the JSON file containing landmark data.
        """

        super().__init__(file_path=file_path)

    def _load_json(self) -> dict:
        """
        Load landmarks data from JSON file.

        Returns
        -------
        dict
            Dictionary containing landmarks and transformation data.
        """
        with open(self.source_data["file_path"], "r") as f:
            data = json.load(f)

        return data

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict | None,
        summary_images_name: str = "SummaryImages",
        source_image_name: str = "MeanImage",
    ) -> None:
        """
        Add landmarks data to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the landmarks will be added.
        metadata : dict | None
            Metadata for the NWB file.
        summary_images_name : str, default: "SummaryImages"
            Name of the container in the NWB file that holds the summary images.
        source_image_name : str, default: "MeanImage"
            Name of the source image within the summary images container.
        """
        from ndx_spatial_transformation import (
            Landmarks,
            SimilarityTransformation,
            SpatialTransformationMetadata,
        )
        from skimage.transform import SimilarityTransform

        data = self._load_json()

        if "transform" not in data:
            raise ValueError("The JSON file must contain a 'transform' key with the transformation matrix.")
        if "landmarks_match" not in data or "landmarks_im" not in data:
            raise ValueError("The JSON file must contain 'landmarks_match' and 'landmarks_im' keys with landmark data.")

        ophys_module = get_module(
            nwbfile=nwbfile,
            name="ophys",
            description="contains optical physiology processed data",
        )
        if summary_images_name not in ophys_module.data_interfaces:
            raise ValueError(
                f"The NWB file must contain '{summary_images_name}' container in the 'ophys' module. First add the processed data using IBLWidefieldSVDInterface."
            )

        if source_image_name not in ophys_module.data_interfaces[summary_images_name].images:
            raise ValueError(
                f"The '{summary_images_name}' container must contain an image named '{source_image_name}'."
            )
        source_image = ophys_module[summary_images_name][source_image_name]

        transform_function = SimilarityTransform(data["transform"])
        # TODO: remove transpose when we save images in height x width format instead of width x height
        source_image_data = source_image.data[:].T  # Transpose to height x width
        target_image_data = im_apply_transform(im=source_image_data, M=transform_function)

        # Store transformed image in GrayscaleImage
        target_image = GrayscaleImage(
            name="MeanImageTransformed",  # TODO: what should we name this?
            description="Transformed frame aligned to Allen CCF coordinates",
            data=target_image_data,
        )
        # Add images to NWB file
        images_container_name = "TransformedImages"
        if images_container_name not in ophys_module.data_interfaces:
            ophys_module.add(Images(name="TransformedImages", description="Contains transformed images."))

        ophys_module.data_interfaces[images_container_name].add_image(target_image)

        # Create landmarks table
        landmarks_table = Landmarks(
            name="Landmarks",
            description="Anatomical landmarks for Allen CCF alignment",
            source_image=source_image,
            target_image=target_image,
        )

        coordinates_source_x = data["landmarks_match"]["x"]
        coordinates_source_y = data["landmarks_match"]["y"]
        coordinates_target_x = data["landmarks_im"]["x"]
        coordinates_target_y = data["landmarks_im"]["y"]
        names = data["landmarks_im"].get("name", [None] * len(coordinates_source_x))
        for source_x, source_y, target_x, target_y, label in zip(
            coordinates_source_x,
            coordinates_source_y,
            coordinates_target_x,
            coordinates_target_y,
            names,
        ):
            row_kwargs = dict(
                source_coordinates=[source_x, source_y],  # coordinates in source image space
                target_coordinates=[target_x, target_y],  # coordinates in atlas (registered) image
            )
            if label:
                row_kwargs.update(landmark_labels=label)
            landmarks_table.add_row(**row_kwargs)

        if "color" in data["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=data["landmarks_match"]["color"],
                description="TODO: add description for color column",
            )

        # Add metadata to NWB file
        spatial_metadata = SpatialTransformationMetadata(name="SpatialTransformationMetadata")

        similarity_transformation = SimilarityTransformation(
            name="SimilarityTransformation",
            rotation_angle=transform_function.rotation,
            translation_vector=transform_function.translation,
            scale=transform_function.scale,
        )
        spatial_metadata.add_spatial_transformations(spatial_transformations=similarity_transformation)
        spatial_metadata.add_landmarks(landmarks=landmarks_table)

        nwbfile.add_lab_meta_data(spatial_metadata)
