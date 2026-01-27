import numpy as np
from iblatlas.atlas import AllenAtlas, BrainCoordinates
from ndx_anatomical_localization import (
    AllenCCFv3Space,
    AnatomicalCoordinatesImage,
    AnatomicalCoordinatesTable,
    Localization,
    Space,
)
from ndx_spatial_transformation import (
    AffineTransformation,
    Landmarks,
    SpatialTransformationMetadata,
)
from neuroconv.tools import get_module
from pydantic import FilePath
from pynwb import NWBFile
from pynwb.base import Images
from pynwb.image import GrayscaleImage
from wfield import allen_load_reference, im_apply_transform, load_allen_landmarks

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
        # ========================================================================
        # Load landmarks from JSON file
        # ========================================================================

        allen_landmarks = load_allen_landmarks(self.source_data["file_path"])

        if "transform" not in allen_landmarks:
            raise ValueError("The JSON file must contain a 'transform' key with the transformation matrix.")
        if "landmarks_match" not in allen_landmarks or "landmarks_im" not in allen_landmarks:
            raise ValueError(
                "The JSON file must contain 'landmarks_match' and 'landmarks_im' keys with the original and transformed landmark data."
            )

        # ========================================================================
        # Access source image from NWB file and apply transformation
        # ========================================================================

        ophys_module = get_module(nwbfile=nwbfile, name="ophys")
        if summary_images_name not in ophys_module.data_interfaces:
            raise ValueError(
                f"The NWB file must contain '{summary_images_name}' container in the 'ophys' module. First add the processed data using IBLWidefieldSVDInterface."
            )

        # Access source image from NWB file
        if source_image_name not in ophys_module.data_interfaces[summary_images_name].images:
            raise ValueError(
                f"The '{summary_images_name}' container must contain an image named '{source_image_name}'."
            )
        source_image = ophys_module[summary_images_name][source_image_name]

        # Apply transformation to source image
        source_image_data = source_image.data[:]
        target_image_data = im_apply_transform(im=source_image_data, M=allen_landmarks["transform"])

        # ========================================================================
        # Store transformed image in NWB file
        # ========================================================================

        target_image = GrayscaleImage(
            name="TransformedMeanImage",
            description="Transformed frame aligned to Allen CCF coordinates.",
            data=target_image_data,
        )
        # Add images to NWB file
        images_container_name = "TransformedImages"
        if images_container_name not in ophys_module.data_interfaces:
            ophys_module.add(
                Images(name=images_container_name, description="Contains images aligned to Allen CCF coordinates.")
            )

        ophys_module.data_interfaces[images_container_name].add_image(target_image)

        # ========================================================================
        # Store reference projection image in NWB file
        # ========================================================================

        # Access atlas projection image from wfield package
        ccf_regions, reference_image_data, _ = allen_load_reference("dorsal_cortex")
        # Store reference image in GrayscaleImage
        reference_image = GrayscaleImage(
            name="ReferenceProjectionImage",
            description="The 2D reference projection image from Allen CCF dorsal cortex.",
            data=reference_image_data,
        )
        ophys_module.data_interfaces[images_container_name].add_image(reference_image)

        # ========================================================================
        # Create and store Landmarks table in NWB file
        # ========================================================================

        landmarks_table = Landmarks(
            name="Landmarks",
            description="Anatomical landmarks for Allen CCF alignment.",
            source_image=source_image,
            target_image=target_image,
            reference_projection_image=reference_image,
        )
        source_coordinates = allen_landmarks["landmarks_match"][["x", "y"]].values
        target_coordinates = allen_landmarks["landmarks_im"][["x", "y"]].values
        landmark_labels = allen_landmarks["landmarks_im"]["name"]

        reference_coordinates = allen_landmarks["landmarks"][["x", "y"]].values * 100  # in pixels
        # Adjust offsets so origin is top left corner
        dorsal_cortex_reference = ccf_regions["reference"].values[0]
        reference_coordinates[:, 1] = (
            reference_coordinates[:, 1] + dorsal_cortex_reference[0]
        )  # (540) adjust for offset in dorsal cortex reference
        reference_coordinates[:, 0] = (
            reference_coordinates[:, 0] + dorsal_cortex_reference[1]
        )  # (570) adjust for offset in dorsal cortex reference

        for source_xy, target_xy, reference_xy, landmark_label in zip(
            source_coordinates,
            target_coordinates,
            reference_coordinates,
            landmark_labels,
        ):
            landmarks_table.add_row(
                source_x=source_xy[0],  # x coordinates in source image space
                source_y=source_xy[1],  # y coordinates in source image space
                target_x=target_xy[0],  # x coordinates in transformed/warped image
                target_y=target_xy[1],  # y coordinates in transformed/warped image
                reference_x=reference_xy[0],  # x coordinates in atlas projection image
                reference_y=reference_xy[1],  # y coordinates in atlas projection image
                landmark_labels=landmark_label,
            )

        if "color" in allen_landmarks["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=allen_landmarks["landmarks_match"]["color"].tolist(),
                description="Color hex code for each landmark.",
            )

        if "bregma_offset" in allen_landmarks:
            bregma_offset_x, bregma_offset_y = allen_landmarks["bregma_offset"]
            landmarks_table.add_column(
                name="bregma_offset_x",
                data=[bregma_offset_x for _ in range(len(landmarks_table))],
                description="X Offset of bregma in pixels.",
            )
            landmarks_table.add_column(
                name="bregma_offset_y",
                data=[bregma_offset_y for _ in range(len(landmarks_table))],
                description="Y Offset of bregma in pixels.",
            )

        if "resolution" in allen_landmarks:
            res_mm_per_px = allen_landmarks["resolution"]  # mm / pixel
            res_um_per_px = res_mm_per_px * 1e3
            landmarks_table.add_column(
                name="resolution",
                data=[res_um_per_px for _ in range(len(landmarks_table))],
                description="Resolution in µm per pixel.",
            )

        # ========================================================================
        # Create SpatialTransformationMetadata and add to NWB file
        # ========================================================================

        spatial_transformation_metadata = SpatialTransformationMetadata(name="SpatialTransformationMetadata")

        transform_function = allen_landmarks["transform"]
        spatial_transformation = AffineTransformation(
            name="AffineTransformation",
            affine_matrix=transform_function.params,
        )
        spatial_transformation_metadata.add_spatial_transformations(spatial_transformations=spatial_transformation)
        spatial_transformation_metadata.add_landmarks(landmarks=landmarks_table)

        nwbfile.add_lab_meta_data(spatial_transformation_metadata)

        return landmarks_table

    def add_anatomical_coordinates_to_nwbfile(
        self,
        nwbfile: NWBFile,
        landmarks: Landmarks,
    ) -> None:
        """Add anatomical coordinate metadata derived from the landmarks.

        This adds:
        - Coordinate spaces (IBL bregma-centered projection + Allen CCFv3)
        - Per-pixel coordinate and region annotation for the transformed mean image
        - Per-landmark coordinate tables in both spaces
        """

        # =====================================================================
        # Load landmarks JSON (needed for CCF conversion below)
        # =====================================================================

        allen_landmarks = load_allen_landmarks(self.source_data["file_path"])

        # =====================================================================
        # Set up coordinate spaces + Localization container
        # =====================================================================

        ibl_bregma_space = Space(
            name="IBLBregmaProjection",
            space_name="IBLBregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        ccf_space = AllenCCFv3Space()

        localization = Localization()
        nwbfile.add_lab_meta_data([localization])
        localization.add_spaces([ibl_bregma_space, ccf_space])

        # =====================================================================
        # Validate required landmarks fields and pull images
        # =====================================================================

        if landmarks.target_image is None:
            raise ValueError("The landmarks table must have a target_image defined.")
        if landmarks.reference_projection_image is None:
            raise ValueError("The landmarks table must have a reference_projection_image defined.")

        target_image = landmarks.target_image
        target_image_data = target_image.data[:]
        reference_image_data = landmarks.reference_projection_image.data[:]

        # Use an annotated landmark as the origin reference point.
        # (This matches the current logic; using index 1 is from IBL code.)
        reference_landmark_index = 1
        xy_warp_px = landmarks[:][["target_x", "target_y"]].values[reference_landmark_index]
        xy_ref_px = landmarks[:][["reference_x", "reference_y"]].values[reference_landmark_index]

        res_um_per_px = float(landmarks["resolution"][0])
        res_ref_um_per_px = 10.0  # wfield dorsal cortex projection is 10 um/px

        # =====================================================================
        # Build BrainCoordinates transforms to map warped pixels -> reference pixels
        # =====================================================================

        # BrainCoordinates expects the origin in physical units.
        warp_origin_um = np.r_[xy_warp_px * res_um_per_px, 0.0]
        ref_origin_um = np.r_[xy_ref_px * res_ref_um_per_px, 0.0]

        # Shapes are [x, y, z] where x=width, y=height.
        bc_warp = BrainCoordinates(
            [target_image_data.shape[1], target_image_data.shape[0], 2],
            xyz0=warp_origin_um,
            dxyz=[-res_um_per_px, -res_um_per_px, res_um_per_px],
        )
        bc_ref = BrainCoordinates(
            [reference_image_data.shape[1], reference_image_data.shape[0], 2],
            xyz0=ref_origin_um,
            dxyz=[-res_ref_um_per_px, -res_ref_um_per_px, res_ref_um_per_px],
        )

        # =====================================================================
        # Compute per-pixel coordinates in IBL bregma space and map to atlas labels
        # =====================================================================

        x_index, y_index = np.meshgrid(np.arange(target_image_data.shape[1]), np.arange(target_image_data.shape[0]))
        coords_flat = np.column_stack((x_index.ravel(), y_index.ravel()))
        zeros = np.zeros((coords_flat.shape[0], 1), dtype=coords_flat.dtype)
        coords_flat = np.hstack((coords_flat, zeros))

        # Convert index to xyz Cartesian coordinates
        xyz_um = bc_warp.i2xyz(coords_flat)
        # Convert xyz coordinates to index coordinates in reference projection
        ref_idx = bc_ref.xyz2i(xyz_um, mode="clip")

        # Region labels (wfield reference image stores region 'label' values)
        # Get the region for each pixel in warped image by looking up in reference projection
        regions = reference_image_data[ref_idx[:, 1], ref_idx[:, 0]]
        regions_image = regions.reshape(target_image_data.shape[0], target_image_data.shape[1])
        xyz_um_image = xyz_um.reshape(target_image_data.shape[0], target_image_data.shape[1], 3)

        # Map label -> allen_id/acronym for storage
        ccf_regions, _, _ = allen_load_reference("dorsal_cortex")
        label_to_acronym = ccf_regions.set_index("label")["acronym"].to_dict()
        label_to_allen_id = ccf_regions.set_index("label")["allen_id"].to_dict()

        brain_region_id_image = np.vectorize(label_to_allen_id.get)(regions_image)
        # replace None with 0 for out-of-atlas regions
        outside_mask = brain_region_id_image == None
        brain_region_id_image[outside_mask] = 0
        brain_region_acronym_image = np.vectorize(label_to_acronym.get)(regions_image)
        brain_region_acronym_image[outside_mask] = "out-of-atlas"

        anatomical_coordinates_image = AnatomicalCoordinatesImage(
            name="TransformedMeanImageAnatomicalCoordinatesIBLBregma",
            description="Transformed mean image estimated coordinates in IBL bregma-centered coordinate system.",
            space=ibl_bregma_space,
            method="IBL manual annotation",  # TODO: confirm method description
            image=target_image,
            x=xyz_um_image[:, :, 0],
            y=xyz_um_image[:, :, 1],
            z=xyz_um_image[:, :, 2],
            brain_region_id=brain_region_id_image,
            brain_region=brain_region_acronym_image,
        )
        localization.add_anatomical_coordinates_images([anatomical_coordinates_image])

        # =====================================================================
        # Create per-landmark coordinate tables in both spaces
        # =====================================================================

        ibl_bregma_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesIBLBregma",
            target=landmarks,
            description=(
                "IBL bregma-centered coordinates of landmarks. Coordinates are in um in the IBL frame "
                "(RAS: x=ML, y=AP, z=DV)."
            ),
            method="IBL manual annotation",
            space=ibl_bregma_space,
        )

        ccf_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesCCFv3",
            target=landmarks,
            description=(
                "CCF coordinates of landmarks. Coordinates are in the native Allen CCF format with PIR+ "
                "orientation (x=AP, y=DV, z=ML)."
            ),
            method="IBL histology alignment pipeline",
            space=ccf_space,
        )

        # allen_landmarks["landmarks"] is in mm relative to bregma.
        # Convert to meters, then to um for IBL table.
        xy_m = allen_landmarks["landmarks"][["x", "y"]].values.astype(float) / 1000.0
        xyz_m = np.hstack((xy_m, np.zeros((xy_m.shape[0], 1), dtype=float)))
        xyz_um_landmarks = xyz_m * 1e6

        # Convert to CCF microns
        atlas = AllenAtlas(res_um=10)
        ccf_um = atlas.xyz2ccf(xyz=xyz_m, ccf_order="apdvml").astype(np.float64)

        for landmark_index in range(len(landmarks)):
            brain_region = landmarks["landmark_labels"][landmark_index]  # keep original labels for now

            ibl_bregma_coordinates_table.add_row(
                x=xyz_um_landmarks[landmark_index, 0],
                y=xyz_um_landmarks[landmark_index, 1],
                z=xyz_um_landmarks[landmark_index, 2],
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

        self.add_anatomical_coordinates_to_nwbfile(
            nwbfile=nwbfile,
            landmarks=landmarks,
        )
