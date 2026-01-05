import numpy as np
from ndx_anatomical_localization import AnatomicalCoordinatesTable, Localization
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
        from ndx_anatomical_localization import (
            AllenCCFv3Space,
        )
        from ndx_spatial_transformation import (
            AffineTransformation,
            Landmarks,
            SpatialTransformationMetadata,
        )
        from wfield import load_allen_landmarks

        allen_landmarks = load_allen_landmarks(self.source_data["file_path"])

        if "transform" not in allen_landmarks:
            raise ValueError("The JSON file must contain a 'transform' key with the transformation matrix.")
        if "landmarks_match" not in allen_landmarks or "landmarks_im" not in allen_landmarks:
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

        source_image_data = source_image.data[:]
        target_image_data = im_apply_transform(im=source_image_data, M=allen_landmarks["transform"])

        # Store transformed image in GrayscaleImage
        target_image = GrayscaleImage(
            name="CCFAlignedMeanImage",
            description="Transformed frame aligned to Allen CCF coordinates",
            data=target_image_data,
        )
        # Add images to NWB file
        images_container_name = "CCFAlignedImages"
        if images_container_name not in ophys_module.data_interfaces:
            ophys_module.add(
                Images(name=images_container_name, description="Contains images aligned to Allen CCF coordinates.")
            )

        ophys_module.data_interfaces[images_container_name].add_image(target_image)

        # Create landmarks table
        landmarks_table = Landmarks(
            name="Landmarks",
            description="Anatomical landmarks for Allen CCF alignment.",
            source_image=source_image,
            target_image=target_image,
        )

        coordinates_source_x = allen_landmarks["landmarks_match"]["x"]
        coordinates_source_y = allen_landmarks["landmarks_match"]["y"]
        coordinates_target_x = allen_landmarks["landmarks_im"]["x"]
        coordinates_target_y = allen_landmarks["landmarks_im"]["y"]
        names = allen_landmarks["landmarks_im"]["name"]
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

        if "color" in allen_landmarks["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=allen_landmarks["landmarks_match"]["color"].tolist(),
                description="Color hex code for each landmark.",
            )

        # Add metadata to NWB file
        spatial_metadata = SpatialTransformationMetadata(name="SpatialTransformationMetadata")

        transform_function = allen_landmarks["transform"]
        spatial_transformation = AffineTransformation(
            name="AffineTransformation",
            affine_matrix=transform_function.params,
        )
        spatial_metadata.add_spatial_transformations(spatial_transformations=spatial_transformation)
        spatial_metadata.add_landmarks(landmarks=landmarks_table)

        nwbfile.add_lab_meta_data(spatial_metadata)

        # TODO: move this to separate function
        # Do we need to store the bregma offset and resolution somewhere?
        #  bregma offset: [320, 270]
        #  resolution: 0.0194
        space = AllenCCFv3Space()
        localization = Localization()
        nwbfile.add_lab_meta_data([localization])
        localization.add_spaces([space])
        anatomical_coordinates_table = AnatomicalCoordinatesTable(
            name="CCFLocalization",
            target=landmarks_table,
            description="CCF coordinates",
            method="manual annotation",
            space=space,
        )
        anatomical_coordinates_table.add_column(
            name="resolution",
            description="Resolution used to convert from image pixels to anatomical coordinates (in mm/px).",
        )
        anatomical_coordinates_table.add_column(
            name="bregma_offset",
            description="Bregma offset in pixel coordinates.",
        )

        landmarks_in_anatomical_registered_space = allen_landmarks["landmarks"]
        landmark_rows = landmarks_in_anatomical_registered_space.values.tolist()
        for localized_entity, row in enumerate(landmark_rows):
            x_um = row[0] * 1000  # convert mm to um
            y_um = row[1] * 1000
            anatomical_coordinates_table.add_row(
                x=x_um,
                y=y_um,
                z=np.nan,  # TODO: why no z coordinate?
                resolution=allen_landmarks["resolution"],  # mm/px
                bregma_offset=allen_landmarks["bregma_offset"],  # px
                brain_region=row[2],  # TODO: how to store the brain region?
                localized_entity=localized_entity,
            )

        localization.add_anatomical_coordinates_tables(anatomical_coordinates_table)
