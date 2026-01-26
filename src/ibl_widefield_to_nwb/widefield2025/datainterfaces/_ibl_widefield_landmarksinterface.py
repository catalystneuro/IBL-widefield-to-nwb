import numpy as np
from ndx_spatial_transformation import Landmarks
from neuroconv.tools import get_module
from pydantic import FilePath
from pynwb import NWBFile
from pynwb.base import Images
from pynwb.image import GrayscaleImage
from wfield import im_apply_transform

from ibl_widefield_to_nwb.widefield2025.datainterfaces._base_ibl_interface import (
    BaseIBLDataInterface,
)


class IblWidefieldLandmarksInterface(BaseIBLDataInterface):
    """Data Interface for storing landmarks from Widefield sessions in NWB."""

    interface_name = "IblWidefieldLandmarksInterface"

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for landmarks data.

        Returns
        -------
        dict
            Data requirements specification with exact file paths
        """
        return {
            "one_objects": [],  # Uses load_dataset directly, not load_object
            "exact_files_options": {
                "standard": [
                    "alf/widefield/widefieldLandmarks.dorsalCortex.json",
                ]
            },
        }

    def __init__(self, file_path: FilePath):
        """
        Initialize the IblWidefieldLandmarksInterface.

        Parameters
        ----------
        file_path: FilePath
            Path to the JSON file containing landmark data.
        """

        super().__init__(file_path=file_path)

    def add_landmarks_to_nwbfile(
        self,
        nwbfile: NWBFile,
        summary_images_name: str,
        source_image_name: str,
    ) -> Landmarks:
        """Add landmarks data to the NWB file.

         Loads landmarks from JSON file, applies transformation to source image,
         and stores transformed image and landmarks in NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the landmarks will be added.
        summary_images_name : str
            Name of the container in the NWB file that holds the summary images.
        source_image_name : str
            Name of the source image within the summary images container.

        Returns
        -------
        Landmarks
            The Landmarks table added to the NWB file.
        """
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
            raise ValueError(
                "The JSON file must contain 'landmarks_match' and 'landmarks_im' keys with the original and transformed landmark data."
            )

        ophys_module = get_module(nwbfile=nwbfile, name="ophys")
        if summary_images_name not in ophys_module.data_interfaces:
            raise ValueError(
                f"The NWB file must contain '{summary_images_name}' container in the 'ophys' module. First add the processed data using IBLWidefieldSVDInterface."
            )

        if source_image_name not in ophys_module.data_interfaces[summary_images_name].images:
            raise ValueError(
                f"The '{summary_images_name}' container must contain an image named '{source_image_name}'."
            )
        source_image = ophys_module[summary_images_name][source_image_name]

        # Apply transformation to source image
        source_image_data = source_image.data[:]
        target_image_data = im_apply_transform(im=source_image_data, M=allen_landmarks["transform"])

        # Store transformed image in GrayscaleImage
        target_image = GrayscaleImage(
            name="TransformedMeanImage",
            description="Transformed frame aligned to Allen CCF coordinates",
            data=target_image_data,
        )
        # Add images to NWB file
        images_container_name = "TransformedImages"
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
        source_coordinates = allen_landmarks["landmarks_match"][["x", "y"]].values
        target_coordinates = allen_landmarks["landmarks_im"][["x", "y"]].values
        landmark_labels = allen_landmarks["landmarks_im"]["name"]
        for source_xy, target_xy, landmark_label in zip(
            source_coordinates,
            target_coordinates,
            landmark_labels,
        ):
            landmarks_table.add_row(
                source_coordinates=source_xy,  # coordinates in source image space
                target_coordinates=target_xy,  # coordinates in atlas (registered) image
                landmark_labels=landmark_label,
            )

        if "color" in allen_landmarks["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=allen_landmarks["landmarks_match"]["color"].tolist(),
                description="Color hex code for each landmark.",
            )

        if "bregma_offset" in allen_landmarks:
            landmarks_table.add_column(
                name="bregma_offset",
                data=[allen_landmarks["bregma_offset"] for _ in range(len(landmarks_table))],
                description="Offset of bregma in pixels.",
            )

        if "resolution" in allen_landmarks:
            res_mm_per_px = allen_landmarks["resolution"]  # mm / pixel
            res_um_per_px = res_mm_per_px * 1e3
            landmarks_table.add_column(
                name="resolution",
                data=[res_um_per_px for _ in range(len(landmarks_table))],
                description="Resolution in µm per pixel.",
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

        return landmarks_table

    def add_anatomical_coordinates_tables_to_nwbfile(
        self,
        nwbfile: NWBFile,
        landmarks: Landmarks,
    ) -> None:
        """
        Add anatomical coordinates tables to the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the anatomical coordinates (IBL Bregma, Allen CCF) will be added.
        landmarks : Landmarks
            The landmarks table containing landmark data.
        """
        from iblatlas.atlas import AllenAtlas
        from ndx_anatomical_localization import (
            AllenCCFv3Space,
            AnatomicalCoordinatesTable,
            Localization,
            Space,
        )
        from wfield import load_allen_landmarks

        allen_landmarks = load_allen_landmarks(self.source_data["file_path"])
        if "landmarks" not in allen_landmarks:
            raise ValueError(
                "The JSON file must contain 'landmarks' key with the anatomical coordinates for the landmarks."
            )

        # Create coordinate spaces
        ibl_bregma_space = Space(
            name="IBLBregmaProjection",
            space_name="IBLBregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        ccf_space = AllenCCFv3Space()

        # Add spaces to NWB file
        localization = Localization()
        nwbfile.add_lab_meta_data([localization])
        localization.add_spaces([ibl_bregma_space, ccf_space])

        # Create anatomical coordinates tables
        ibl_bregma_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesIBLBregma",
            target=landmarks,
            description="IBL Bregma-centered coordinates of landmarks. Coordinates are in um in the IBL frame (RAS: x=ML, y=AP, z=DV).",
            method="IBL manual annotation",
            space=ibl_bregma_space,
        )

        ccf_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesCCFv3",
            target=landmarks,
            description="CCF coordinates of landmarks. Coordinates are in the native Allen CCF format with PIR+ orientation (x=AP, y=DV, z=ML).",
            method="IBL histology alignment pipeline",
            space=ccf_space,
        )

        # allen_landmarks["landmarks"] is in mm relative to bregma
        xy_m = allen_landmarks["landmarks"][["x", "y"]].values / 1000.0
        # Coordinates in meters in the IBL frame (RAS: x=ML, y=AP, z=DV).
        # add z=0 for 2D projection
        xyz_m = np.hstack((xy_m, np.zeros((xy_m.shape[0], 1))))

        # Convert to CCF coordinates
        atlas = AllenAtlas(res_um=10)
        # IBL coordinates: x - ml, y - ap, z - dv (in this case one pixel only)
        # (um, origin is the front left top corner of the data volume, order determined by ccf_order
        ccf_um = atlas.xyz2ccf(xyz=xyz_m, ccf_order="apdvml").astype(np.float64)
        xyz_um = xyz_m * 1e6

        num_landmarks = len(landmarks)
        for landmark_index in range(num_landmarks):
            brain_region = landmarks["landmark_labels"][landmark_index]  # uses landmarks labels as is for now

            ibl_bregma_coordinates_table.add_row(
                x=xyz_um[landmark_index, 0],
                y=xyz_um[landmark_index, 1],
                z=xyz_um[landmark_index, 2],
                brain_region=brain_region,
                localized_entity=landmark_index,
            )

            ccf_coordinates_table.add_row(
                x=ccf_um[landmark_index, 0],
                y=ccf_um[landmark_index, 1],
                z=ccf_um[landmark_index, 2],
                brain_region=brain_region,
                localized_entity=landmark_index,
            )

        # Add both tables to localization
        localization.add_anatomical_coordinates_tables([ibl_bregma_coordinates_table, ccf_coordinates_table])

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

        landmarks = self.add_landmarks_to_nwbfile(
            nwbfile=nwbfile,
            summary_images_name=summary_images_name,
            source_image_name=source_image_name,
        )

        self.add_anatomical_coordinates_tables_to_nwbfile(
            nwbfile=nwbfile,
            landmarks=landmarks,
        )
