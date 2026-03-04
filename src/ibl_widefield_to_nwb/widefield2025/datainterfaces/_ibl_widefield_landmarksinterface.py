import numpy as np
from iblatlas.atlas import AllenAtlas, BrainCoordinates
from ndx_anatomical_localization import (
    AffineTransformation,
    AllenCCFv3Space,
    AnatomicalCoordinatesImage,
    AnatomicalCoordinatesTable,
    AtlasRegistration,
    BrainRegionMasks,
    Landmarks,
    Localization,
    Space,
)
from neuroconv.tools import get_module
from one.api import ONE
from pynwb import NWBFile
from pynwb.base import Images
from pynwb.image import GrayscaleImage
from skimage.transform import warp
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

    def __init__(self, one: ONE, session: str):
        """
        Initialize the IblWidefieldLandmarksInterface.

        Parameters
        ----------
        one : ONE
            The ONE instance for data access.
        session : str
            The session ID (eid) for which to load the landmarks data.
        """

        session_path = one.eid2path(session)

        self.file_path = session_path / "alf" / "widefield" / "widefieldLandmarks.dorsalCortex.json"
        assert self.file_path.is_file(), f"Landmarks JSON file not found at expected path: {self.file_path}"

        self.landmarks = load_allen_landmarks(self.file_path)
        self.ccf_regions, self.atlas_projection, _ = allen_load_reference("dorsal_cortex")
        self.source_image = None
        self.registered_image = None
        self.ibl_bregma_space = Space(
            name="IBLBregmaProjection",
            space_name="IBLBregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        self.allen_ccf_space = AllenCCFv3Space()

        super().__init__(one=one, session=session)

    def _build_landmarks_table(self) -> Landmarks:
        """
        Build a fully-populated Landmarks table from raw JSON landmark data.

        Parameters
        ----------
        landmarks : dict
            Parsed landmarks dict from ``load_allen_landmarks``.
        ccf_regions : DataFrame
            CCF region table from ``allen_load_reference``.

        Returns
        -------
        Landmarks
            Fully-populated Landmarks object.
        """
        if "transform" not in self.landmarks:
            raise ValueError("The JSON file must contain a 'transform' key with the transformation matrix.")
        if "landmarks_match" not in self.landmarks or "landmarks_im" not in self.landmarks:
            raise ValueError(
                "The JSON file must contain 'landmarks_match' and 'landmarks_im' keys with the original and transformed landmark data."
            )

        landmarks_table = Landmarks(
            name="landmarks",
            description="Anatomical landmarks for Allen CCF alignment. Origin (0, 0) corresponds to the top-left corner of the image.",
        )
        source_coordinates = self.landmarks["landmarks_match"][["x", "y"]].values
        registered_coordinates = self.landmarks["landmarks_im"][["x", "y"]].values
        landmark_labels = self.landmarks["landmarks_im"]["name"]
        num_landmarks = len(landmark_labels)

        reference_coordinates = self.landmarks["landmarks"][["x", "y"]].values * 100  # in pixels
        # Adjust offsets so origin is top left corner
        dorsal_cortex_reference = self.ccf_regions["reference"].values[0]
        reference_coordinates[:, 1] = (
            reference_coordinates[:, 1] + dorsal_cortex_reference[0]
        )  # (540) adjust for offset in dorsal cortex reference
        reference_coordinates[:, 0] = (
            reference_coordinates[:, 0] + dorsal_cortex_reference[1]
        )  # (570) adjust for offset in dorsal cortex reference

        for source_xy, target_xy, reference_xy, landmark_label in zip(
            source_coordinates,
            registered_coordinates,
            reference_coordinates,
            landmark_labels,
        ):
            landmarks_table.add_row(
                source_x=source_xy[0],  # x coordinates in source image space
                source_y=source_xy[1],  # y coordinates in source image space
                registered_x=target_xy[0],  # x coordinates in transformed/warped image
                registered_y=target_xy[1],  # y coordinates in transformed/warped image
                reference_x=reference_xy[0],  # x coordinates in atlas projection image
                reference_y=reference_xy[1],  # y coordinates in atlas projection image
                landmark_labels=landmark_label,
            )

        if "color" in self.landmarks["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=self.landmarks["landmarks_match"]["color"].tolist(),
                description="Color hex code for each landmark.",
            )

        if "bregma_offset" in self.landmarks:
            bregma_offset_x, bregma_offset_y = self.landmarks["bregma_offset"]
            landmarks_table.add_column(
                name="bregma_offset_x",
                data=[bregma_offset_x for _ in range(num_landmarks)],
                description="X Offset of bregma in pixels.",
            )
            landmarks_table.add_column(
                name="bregma_offset_y",
                data=[bregma_offset_y for _ in range(num_landmarks)],
                description="Y Offset of bregma in pixels.",
            )

        if "resolution" in self.landmarks:
            res_mm_per_px = self.landmarks["resolution"]  # mm / pixel
            res_um_per_px = res_mm_per_px * 1e3
            landmarks_table.add_column(
                name="resolution",
                data=[res_um_per_px for _ in range(num_landmarks)],
                description="Resolution in µm per pixel.",
            )

        return landmarks_table

    def _add_registered_images(
        self,
        nwbfile: NWBFile,
        summary_images_name: str,
        source_image_name: str,
    ):
        """Build registered and atlas projection images, adding them to the ophys module.

        Validates that the required source image exists, applies the affine transform,
        creates a ``RegisteredImages`` container in the ``ophys`` module, and populates
        it with the registered FOV image and the Allen atlas projection image.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file whose ``ophys`` module receives the ``RegisteredImages`` container.
        summary_images_name : str
            Name of the existing ``Images`` container in the ``ophys`` module.
        source_image_name : str
            Name of the source image within that container.

        Returns
        -------
        tuple[GrayscaleImage, GrayscaleImage, GrayscaleImage, np.ndarray, np.ndarray]
            ``(source_image, registered_image, atlas_projection,
               source_image_data, registered_image_data)``
        """
        ophys_module = get_module(nwbfile=nwbfile, name="ophys")
        if summary_images_name not in ophys_module.data_interfaces:
            raise ValueError(
                f"The NWB file must contain '{summary_images_name}' container in the 'ophys' module. "
                "First add the processed data using IBLWidefieldSVDInterface."
            )
        if source_image_name not in ophys_module.data_interfaces[summary_images_name].images:
            raise ValueError(
                f"The '{summary_images_name}' container must contain an image named '{source_image_name}'."
            )

        source_image = ophys_module[summary_images_name][source_image_name]
        self.source_image = source_image.data[:]
        self.registered_image = im_apply_transform(im=self.source_image, M=self.landmarks["transform"])

        registered_image = GrayscaleImage(
            name="RegisteredImage",
            description="Post-registration FOV image.",
            data=self.registered_image,
        )
        atlas_projection = GrayscaleImage(
            name="AtlasProjectionImage",
            description="The 2D reference projection image from Allen CCF dorsal cortex.",
            data=self.atlas_projection,
        )

        images_container_name = "RegisteredImages"
        if images_container_name not in ophys_module.data_interfaces:
            ophys_module.add(Images(name=images_container_name, description="Contains post-registration FOV images."))
        ophys_module.data_interfaces[images_container_name].add_image(registered_image)
        ophys_module.data_interfaces[images_container_name].add_image(atlas_projection)

    def _add_coordinate_spaces(self, nwbfile: NWBFile):
        """Add coordinate spaces to the NWB file.

        Creates Space objects for the IBL bregma-centered coordinate system and the Allen CCF space,
        and adds them to a Localization container in the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to which the coordinate spaces will be added.
        """

        if "localization" not in nwbfile.lab_meta_data:
            nwbfile.add_lab_meta_data([Localization()])

        localization = nwbfile.lab_meta_data["localization"]
        localization.add_spaces([self.ibl_bregma_space, self.allen_ccf_space])

    def _build_anatomical_coordinates_image(
        self,
        nwbfile: NWBFile,
        landmarks: Landmarks,
    ) -> tuple:
        """Compute per-pixel IBL bregma coordinates and build an AnatomicalCoordinatesImage.

        Uses ``BrainCoordinates`` transforms to convert every pixel in the registered
        image to a physical (x, y, z) position in the IBL bregma space, looks up
        the corresponding Allen atlas region label, and packages everything into an
        ``AnatomicalCoordinatesImage``.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file containing the registered image and atlas projection in the ophys module.
        landmarks : Landmarks
            The Landmarks table containing the landmark correspondences and resolution information.

        Returns
        -------
        tuple[AnatomicalCoordinatesImage, np.ndarray]
            ``(anatomical_coordinates_image, brain_region_id_image)``
            where ``brain_region_id_image`` contains Allen IDs per pixel (0 = outside atlas).
        """
        reference_landmark_index = 1

        warp_coords_px = landmarks[:][["registered_x", "registered_y"]].values[reference_landmark_index]
        reference_coords_px = landmarks[:][["reference_x", "reference_y"]].values[reference_landmark_index]

        image_resolution = float(landmarks["resolution"][0])
        warp_origin_coords_um = np.r_[warp_coords_px * image_resolution, 0.0]

        reference_resolution = self.ccf_regions["resolution"].values.astype(float)[0]  # in um / pixel
        reference_origin_coords_um = np.r_[reference_coords_px * reference_resolution, 0.0]

        # BrainCoordinates expects shapes are [x, y, z] where x=width, y=height.
        brain_coordinates_warp = BrainCoordinates(
            [self.registered_image.shape[1], self.registered_image.shape[0], 2],
            xyz0=warp_origin_coords_um,
            dxyz=[-image_resolution, -image_resolution, image_resolution],
        )
        brain_coordinates_reference = BrainCoordinates(
            [self.atlas_projection.shape[1], self.atlas_projection.shape[0], 2],
            xyz0=reference_origin_coords_um,
            dxyz=[-reference_resolution, -reference_resolution, reference_resolution],
        )

        x_index, y_index = np.meshgrid(
            np.arange(self.registered_image.shape[1]), np.arange(self.registered_image.shape[0])
        )
        coords_flat = np.column_stack((x_index.ravel(), y_index.ravel()))
        zeros = np.zeros((coords_flat.shape[0], 1), dtype=coords_flat.dtype)
        coords_flat = np.hstack((coords_flat, zeros))

        xyz_um = brain_coordinates_warp.i2xyz(coords_flat)
        ref_idx = brain_coordinates_reference.xyz2i(xyz_um, mode="clip")

        regions = self.atlas_projection[ref_idx[:, 1], ref_idx[:, 0]]
        regions_image = regions.reshape(self.registered_image.shape[0], self.registered_image.shape[1])
        xyz_um_image = xyz_um.reshape(self.registered_image.shape[0], self.registered_image.shape[1], 3)

        label_to_allen_id = self.ccf_regions.set_index("label")["allen_id"].to_dict()
        brain_region_id_image = np.vectorize(label_to_allen_id.get)(regions_image)
        outside_mask = brain_region_id_image == None  # noqa: E711
        brain_region_id_image[outside_mask] = 0

        label_to_acronym = self.ccf_regions.set_index("label")["acronym"].to_dict()
        brain_region_acronym_image = np.vectorize(label_to_acronym.get)(regions_image)
        brain_region_acronym_image[outside_mask] = "out-of-atlas"

        registered_image = nwbfile.processing["ophys"]["RegisteredImages"]["RegisteredImage"]
        anatomical_coordinates_image = AnatomicalCoordinatesImage(
            name="RegisteredImageAnatomicalCoordinatesIBLBregma",
            description="Transformed mean image estimated coordinates in IBL bregma-centered coordinate system.",
            space=self.ibl_bregma_space,
            method="IBL manual annotation",  # TODO: confirm method description
            image=registered_image,
            x=xyz_um_image[:, :, 0],
            y=xyz_um_image[:, :, 1],
            z=xyz_um_image[:, :, 2],
            brain_region=brain_region_acronym_image,
        )

        return anatomical_coordinates_image, brain_region_id_image

    def _build_brain_region_masks(
        self,
        brain_region_id_image: np.ndarray,
    ) -> tuple:
        """Build BrainRegionMasks for the registered image and the source image.

        Constructs pixel-level brain-region mask tables in both spaces. The
        source-space masks are obtained by warping the registered-space label
        image back through the inverse affine transform.

        Parameters
        ----------
        brain_region_id_image : np.ndarray
            Per-pixel Allen IDs in registered space (0 = outside atlas).

        Returns
        -------
        tuple[BrainRegionMasks, BrainRegionMasks]
            ``(registered_masks, source_masks)``
        """
        # Registered-space masks
        ys, xs = brain_region_id_image.nonzero()
        registered_masks = BrainRegionMasks(
            name="RegisteredImageBrainRegionMasksIBLBregma",
            description="Brain region masks for each pixel in the registered image based on the atlas projection.",
        )
        for y, x in zip(ys, xs):
            registered_masks.add_row(
                x=int(x), y=int(y), brain_region_id=int(brain_region_id_image[y, x]), check_ragged=False
            )

        # Source-space masks (warp allen_id image back using nearest-neighbour interpolation;
        # order=0 preserves discrete region IDs exactly — no blending between regions).
        source_brain_region_id_image = warp(
            brain_region_id_image.astype(np.float64),
            inverse_map=self.landmarks["transform"].inverse,
            output_shape=self.source_image.shape,
            order=0,
            preserve_range=True,
        ).astype(np.int64)
        ys_src, xs_src = (source_brain_region_id_image != 0).nonzero()
        source_masks = BrainRegionMasks(
            name="SourceImageBrainRegionMasksIBLBregma",
            description="Brain region masks for each pixel in the source image, warped back from registered space via inverse transform.",
        )
        for y, x in zip(ys_src, xs_src):
            source_masks.add_row(
                x=int(x), y=int(y), brain_region_id=int(source_brain_region_id_image[y, x]), check_ragged=False
            )

        return registered_masks, source_masks

    def _build_landmark_coordinate_tables(
        self,
        landmarks: Landmarks,
    ) -> tuple:
        """Build AnatomicalCoordinatesTables in IBL bregma space and CCF space.

        Parameters
        ----------
        landmarks : Landmarks
            The Landmarks table to which these coordinate rows will refer.
        ibl_bregma_space : Space
            The IBL bregma coordinate space object.
        ccf_space : AllenCCFv3Space
            The Allen CCF v3 coordinate space object.
        allen_landmarks : dict
            Parsed landmarks dict; ``allen_landmarks["landmarks"]`` contains mm
            bregma-relative coordinates for each landmark.

        Returns
        -------
        tuple[AnatomicalCoordinatesTable, AnatomicalCoordinatesTable]
            ``(ibl_bregma_table, ccf_table)``
        """
        ibl_bregma_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesIBLBregma",
            target=landmarks,
            description=(
                "IBL bregma-centered coordinates of landmarks. Coordinates are in um in the IBL frame "
                "(RAS: x=ML, y=AP, z=DV)."
            ),
            method="IBL manual annotation",
            space=self.ibl_bregma_space,
        )
        ccf_coordinates_table = AnatomicalCoordinatesTable(
            name="AnatomicalCoordinatesCCFv3",
            target=landmarks,
            description=(
                "CCF coordinates of landmarks. Coordinates are in the native Allen CCF format with PIR+ "
                "orientation (x=AP, y=DV, z=ML)."
            ),
            method="IBL manual annotation",
            space=self.allen_ccf_space,
        )

        # allen_landmarks["landmarks"] is in mm relative to bregma.
        # Convert to meters, then to um for IBL table.
        xy_m = self.landmarks["landmarks"][["x", "y"]].values.astype(float) / 1000.0
        xyz_m = np.hstack((xy_m, np.zeros((xy_m.shape[0], 1), dtype=float)))
        xyz_um_landmarks = xyz_m * 1e6

        # Convert to CCF microns
        atlas = AllenAtlas(res_um=10)
        ccf_um = atlas.xyz2ccf(xyz=xyz_m, ccf_order="apdvml").astype(np.float64)

        for landmark_index in range(len(landmarks)):
            brain_region = landmarks["landmark_labels"][landmark_index]

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

        return ibl_bregma_coordinates_table, ccf_coordinates_table

    def add_atlas_registration_to_nwbfile(
        self,
        nwbfile: NWBFile,
        summary_images_name: str,
        source_image_name: str,
    ):
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
        """

        # Build Landmarks table
        landmarks = self._build_landmarks_table()

        # Add registered images to ophys module
        self._add_registered_images(
            nwbfile=nwbfile,
            summary_images_name=summary_images_name,
            source_image_name=source_image_name,
        )

        # Set up coordinate spaces
        self._add_coordinate_spaces(nwbfile=nwbfile)
        localization = nwbfile.lab_meta_data["localization"]

        # Build AnatomicalCoordinatesImage + raw brain_region_id array
        anatomical_coordinates_image, brain_region_id_image = self._build_anatomical_coordinates_image(
            nwbfile=nwbfile,
            landmarks=landmarks,
        )
        localization.add_anatomical_coordinates_images([anatomical_coordinates_image])

        # Build BrainRegionMasks for registered and source spaces
        registered_masks, source_masks = self._build_brain_region_masks(brain_region_id_image=brain_region_id_image)
        localization.add_brain_region_masks([registered_masks, source_masks])

        # Assemble AtlasRegistration
        # Now that all linked objects exist (AnatomicalCoordinatesImage +
        # BrainRegionMasks are owned by Localization), AtlasRegistration can
        # hold links to them alongside the affine transform and landmarks.
        ophys = get_module(nwbfile=nwbfile, name="ophys")
        source_image = ophys[summary_images_name][source_image_name]
        registered_image = ophys["RegisteredImages"]["RegisteredImage"]
        atlas_projection = ophys["RegisteredImages"]["AtlasProjectionImage"]

        affine_transformation = AffineTransformation(
            name="AffineTransformation",
            affine_matrix=self.landmarks["transform"].params,
        )

        atlas_registration = AtlasRegistration(
            source_image=source_image,
            registered_image=registered_image,
            atlas_projection=atlas_projection,
            affine_transformation=affine_transformation,
            landmarks=landmarks,
        )
        nwbfile.add_lab_meta_data([atlas_registration])

        # Build and register landmark coordinate tables
        ibl_table, ccf_table = self._build_landmark_coordinate_tables(landmarks=landmarks)
        localization.add_anatomical_coordinates_tables([ibl_table, ccf_table])

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
            Name of the source image within the summary images' container.
        """

        self.add_atlas_registration_to_nwbfile(
            nwbfile=nwbfile,
            summary_images_name=summary_images_name,
            source_image_name=source_image_name,
        )
