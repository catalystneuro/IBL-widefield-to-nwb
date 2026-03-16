import pandas as pd
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
                    "alf/widefield/widefieldChannels.frameAverage.npy",
                    "alf/widefield/imagingLightSource.properties.htsv",
                    "alf/widefield/imaging.imagingLightSource.npy",
                ]
            },
        }

    def __init__(self, one: ONE, session: str, excitation_wavelength_nm: int = 470):
        """
        Initialize the IblWidefieldLandmarksInterface.

        Parameters
        ----------
        one : ONE
            The ONE instance for data access.
        session : str
            The session ID (eid) for which to load the landmarks data.
        excitation_wavelength_nm : int, default: 470
            Excitation wavelength (nm) of the channel whose frame average is used as the
            source image for atlas registration. Only relevant when no pre-existing mean
            image is found in the NWB file (e.g. in the raw conversion pipeline).
        """
        self.excitation_wavelength_nm = excitation_wavelength_nm

        session_path = one.eid2path(session)

        self.file_path = session_path / "alf" / "widefield" / "widefieldLandmarks.dorsalCortex.json"
        assert self.file_path.is_file(), f"Landmarks JSON file not found at expected path: {self.file_path}"

        # Load the JSON landmarks file into a dict. Expected keys:
        #   "landmarks"       – DataFrame [name, x, y] with bregma-relative coords in mm
        #   "landmarks_im"    – DataFrame [name, x, y] with pixel coords in the REGISTERED image
        #   "landmarks_match" – DataFrame [name, x, y] with pixel coords in the SOURCE image
        #   "transform"       – skimage AffineTransform: source → registered space
        #   "bregma_offset"   – (x_px, y_px) pixel location of bregma in the source image
        #   "resolution"      – scalar, source image resolution in mm/pixel
        self.landmarks = load_allen_landmarks(self.file_path)

        # Load the Allen CCF dorsal-cortex reference atlas.
        #   ccf_regions      – DataFrame with columns: label, allen_id, acronym, reference, resolution
        #                       "reference" = (row_offset, col_offset) of the dorsal-cortex crop in the full atlas (pixels)
        #                       "resolution" = atlas pixel size in um/pixel
        #   atlas_projection – 2-D image whose pixel values are integer region "labels" (NOT Allen IDs)
        #                       labels can be mapped to Allen IDs via ccf_regions["label"] → ccf_regions["allen_id"]
        self.ccf_regions, self.atlas_projection, _ = allen_load_reference("dorsal_cortex")

        self.source_image = None  # populated later in _add_registered_images
        self.registered_image = None  # populated later in _add_registered_images

        # IBL bregma-centred space: origin = bregma, units = um, orientation = RAS
        #   x = ML (mediolateral, +right), y = AP (anteroposterior, +anterior), z = DV (+dorsal)
        self.ibl_bregma_space = Space(
            name="IBLBregmaProjection",
            space_name="IBLBregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        self.allen_ccf_space = AllenCCFv3Space()  # standard Allen CCF v3 space (PIR+ orientation)

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

        # Pixel [x, y] of each landmark in the raw SOURCE image (before the affine transform)
        source_coordinates = self.landmarks["landmarks_match"][["x", "y"]].values

        # Pixel [x, y] of each landmark in the REGISTERED image (after the affine transform)
        registered_coordinates = self.landmarks["landmarks_im"][["x", "y"]].values

        landmark_labels = self.landmarks["landmarks_im"]["name"]
        num_landmarks = len(landmark_labels)

        # Convert bregma-relative coords (mm) → pixel coords in the ATLAS PROJECTION image.
        # landmarks["landmarks"][["x","y"]] is in mm; multiplying by 100 converts to pixels
        # assuming 10 um/pixel resolution (1 mm / 0.01 mm·px⁻¹ = 100 px).
        # NOTE: this implicitly assumes the atlas resolution is exactly 10 um/px.
        reference_coordinates = self.landmarks["landmarks"][["x", "y"]].values * 100  # mm → pixels at 10 um/px

        # The atlas_projection is a crop of the full CCF dorsal-cortex image.
        # dorsal_cortex_reference = [row_offset, col_offset] of that crop (i.e. [y_offset, x_offset] in pixels).
        dorsal_cortex_reference = self.ccf_regions["reference"].values[0]

        # Shift the pixel coords from full-atlas space into atlas-projection-image space
        # by adding the crop offsets.
        # column 1 = y (row) ← row_offset = dorsal_cortex_reference[0]
        # column 0 = x (col) ← col_offset = dorsal_cortex_reference[1]
        # NOTE: this mapping is only correct if dorsal_cortex_reference is [row, col].
        # If it were [col, row] the x/y assignment would be swapped — worth verifying.
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
                source_x=source_xy[0],  # x pixel in source image
                source_y=source_xy[1],  # y pixel in source image
                registered_x=target_xy[0],  # x pixel in registered (warped) image
                registered_y=target_xy[1],  # y pixel in registered (warped) image
                reference_x=reference_xy[0],  # x pixel in atlas projection image
                reference_y=reference_xy[1],  # y pixel in atlas projection image
                landmark_labels=landmark_label,
            )

        if "color" in self.landmarks["landmarks_match"]:
            landmarks_table.add_column(
                name="color",
                data=self.landmarks["landmarks_match"]["color"].tolist(),
                description="Color hex code for each landmark.",
            )

        if "bregma_offset" in self.landmarks:
            bregma_offset_x, bregma_offset_y = self.landmarks[
                "bregma_offset"
            ]  # pixel location of bregma in source image
            landmarks_table.add_column(
                name="bregma_offset_x",
                data=[bregma_offset_x for _ in range(num_landmarks)],  # same value repeated for every row
                description="X Offset of bregma in pixels.",
            )
            landmarks_table.add_column(
                name="bregma_offset_y",
                data=[bregma_offset_y for _ in range(num_landmarks)],  # same value repeated for every row
                description="Y Offset of bregma in pixels.",
            )

        if "resolution" in self.landmarks:
            res_mm_per_px = self.landmarks["resolution"]  # source image resolution in mm/pixel
            res_um_per_px = res_mm_per_px * 1e3  # convert to um/pixel
            landmarks_table.add_column(
                name="resolution",
                data=[res_um_per_px for _ in range(num_landmarks)],  # same value repeated for every row
                description="Resolution in µm per pixel.",
            )

        return landmarks_table

    def _load_mean_image_data(self) -> np.ndarray:
        """Load the mean (frame-average) image for the configured excitation wavelength.

        Replicates the logic used by ``WidefieldSVDExtractor._load_mean_image`` so that
        the landmarks interface can obtain a source image even when the SVD processed data
        has not been written to the NWB file (e.g. in the raw conversion pipeline).

        Returns
        -------
        np.ndarray
            2-D mean image array with shape ``(height, width)``.
        """
        alf_folder = self.file_path.parent

        frame_average_file = alf_folder / "widefieldChannels.frameAverage.npy"
        props_file = alf_folder / "imagingLightSource.properties.htsv"
        light_source_file = alf_folder / "imaging.imagingLightSource.npy"

        all_props = pd.read_csv(props_file)
        channel_props = all_props[all_props["wavelength"] == self.excitation_wavelength_nm]  # filter by wavelength
        if len(channel_props) == 0:
            raise ValueError(
                f"No channel found for excitation wavelength {self.excitation_wavelength_nm} nm " f"in '{props_file}'."
            )
        channel_id = channel_props.iloc[0]["channel_id"]  # integer ID of the matching light-source channel

        light_sources = np.load(light_source_file, allow_pickle=True)  # per-frame channel ID array
        frame_indices = np.where(light_sources == channel_id)[0]  # find all frames acquired with this channel
        if len(frame_indices) == 0:
            raise ValueError(
                f"No frames found for channel_id {channel_id} (wavelength "
                f"{self.excitation_wavelength_nm} nm) in '{light_source_file}'."
            )
        first_frame_index = frame_indices[0]  # index of the first frame from this channel

        mean_images = np.load(frame_average_file)  # shape: (n_channels, height, width) — one mean image per channel
        mean_image = mean_images[first_frame_index, ...]  # select the mean image for the chosen channel
        return mean_image

    def _ensure_source_image_in_nwbfile(
        self,
        nwbfile: NWBFile,
        summary_images_name: str,
        source_image_name: str,
    ) -> None:
        """Ensure the source image used for registration exists in the ophys module.

        If the ``Images`` container or the named image is absent (as is the case in the
        raw conversion pipeline where no SVD data is written), the method loads the mean
        frame-average image from disk and inserts it into the ophys module.

        Parameters
        ----------
        nwbfile : NWBFile
            Target NWB file.
        summary_images_name : str
            Name of the ``Images`` container in the ``ophys`` module.
        source_image_name : str
            Name of the source image within that container.
        """
        ophys_module = get_module(nwbfile=nwbfile, name="ophys")

        if summary_images_name not in ophys_module.data_interfaces:  # create container if missing
            ophys_module.add(Images(name=summary_images_name, description="Summary images from widefield imaging."))

        images_container = ophys_module.data_interfaces[summary_images_name]
        if source_image_name not in images_container.images:  # load and insert source image if missing
            mean_image_data = self._load_mean_image_data()
            images_container.add_image(
                GrayscaleImage(
                    name=source_image_name,
                    description="Mean fluorescence image computed as the per-channel frame average.",
                    data=mean_image_data,
                )
            )

    def _add_registered_images(
        self,
        nwbfile: NWBFile,
        summary_images_name: str,
        source_image_name: str,
    ):
        """Build registered and atlas projection images, adding them to the ophys module.

        If the source image does not already exist in the ophys module (e.g. in the raw
        conversion pipeline), it is loaded from the frame-average file on disk before the
        affine transform is applied.  Creates an ``Images`` container in the
        ``ophys`` module and populates it with the registered FOV image and the Allen atlas
        projection image.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file whose ``ophys`` module receives the ``Images`` container.
        summary_images_name : str
            Name of the ``Images`` container in the ``ophys`` module.
        source_image_name : str
            Name of the source image within that container.

        """
        self._ensure_source_image_in_nwbfile(  # guarantee source image exists before reading it
            nwbfile=nwbfile,
            summary_images_name=summary_images_name,
            source_image_name=source_image_name,
        )
        ophys_module = get_module(nwbfile=nwbfile, name="ophys")

        source_image = ophys_module[summary_images_name][source_image_name]
        self.source_image = source_image.data[:]  # store source image as a plain numpy array for later use

        # Apply the affine transform to warp the source image into the atlas projection frame.
        # self.landmarks["transform"] is a skimage AffineTransform (source → registered).
        self.registered_image = im_apply_transform(im=self.source_image, M=self.landmarks["transform"])

        registered_image = GrayscaleImage(
            name="RegisteredImage",
            description="Post-registration FOV image.",
            data=self.registered_image,
        )
        atlas_projection = GrayscaleImage(
            name="AtlasProjectionImage",
            description="The 2D reference projection image from Allen CCF dorsal cortex.",
            data=self.atlas_projection,  # the integer-label image loaded from allen_load_reference
        )

        images_container_name = "Images"
        if images_container_name not in ophys_module.data_interfaces:  # create container if missing
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

        if "localization" not in nwbfile.lab_meta_data:  # create Localization container if missing
            nwbfile.add_lab_meta_data([Localization()])

        localization = nwbfile.lab_meta_data["localization"]
        localization.add_spaces([self.ibl_bregma_space, self.allen_ccf_space])  # register both coordinate spaces

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
        # Index of the landmark used to anchor pixel coords to physical coords in both image spaces.
        # NOTE: hardcoded as 1 — verify this is the correct anchor (ideally bregma, i.e. x=0,y=0 mm).
        reference_landmark_index = 1

        # Pixel [x, y] of the anchor landmark in the REGISTERED image (from landmarks_im)
        warp_coords_px = landmarks[:][["registered_x", "registered_y"]].values[reference_landmark_index]

        # Pixel [x, y] of the anchor landmark in the ATLAS PROJECTION image (from reference_x/y built in _build_landmarks_table)
        reference_coords_px = landmarks[:][["reference_x", "reference_y"]].values[reference_landmark_index]

        # Resolution of the registered/source image in um/pixel (stored in the landmarks table)
        image_resolution = float(landmarks["resolution"][0])

        # Physical (IBL bregma) coordinates of the anchor landmark in um.
        # landmarks["landmarks"][["x","y"]] is in mm; multiply by 1000 → um. z=0 (dorsal surface).
        xy_mm = self.landmarks["landmarks"][["x", "y"]].values.astype(float)
        xyz_um_ref_landmark = np.r_[xy_mm[reference_landmark_index] * 1000.0, 0.0]  # mm → um, shape (3,)

        # Compute xyz0: the physical coordinate at pixel (0,0) of the REGISTERED image.
        # BrainCoordinates model: physical = xyz0 + dxyz * pixel_index
        # dxyz[x] = +res  → as column index increases, ML coord increases (left→right)
        # dxyz[y] = +res  → as row index increases, AP coord increases (top→bottom = anterior→posterior)
        #                    NOTE: in this dataset's IBL convention, POSTERIOR = POSITIVE y
        #                    (OB anterior to bregma → y = -3450 µm; RSP posterior → y = +3200 µm)
        # At the anchor landmark:
        #   anchor_x_um = xyz0[x] + res * px_col  →  xyz0[x] = anchor_x_um - res * px_col
        #   anchor_y_um = xyz0[y] + res * px_row  →  xyz0[y] = anchor_y_um - res * px_row
        warp_origin_coords_um = (
            xyz_um_ref_landmark
            - np.r_[
                image_resolution * warp_coords_px[0],  # xyz0[x] = anchor_x_um - res * anchor_px_col
                image_resolution * warp_coords_px[1],  # xyz0[y] = anchor_y_um - res * anchor_px_row
                0.0,
            ]
        )

        # Resolution of the CCF atlas projection in um/pixel
        reference_resolution = self.ccf_regions["resolution"].values.astype(float)[0]  # in um / pixel

        # Same formula for the ATLAS PROJECTION coordinate system.
        reference_origin_coords_um = (
            xyz_um_ref_landmark
            - np.r_[
                reference_resolution * reference_coords_px[0],
                reference_resolution * reference_coords_px[1],
                0.0,
            ]
        )

        # BrainCoordinates(shape, xyz0, dxyz):
        #   shape = [width, height, depth]  (note: x = columns, y = rows)
        #   xyz0  = physical coord at pixel (0, 0, 0)
        #   dxyz  = [+res, +res, res]  →  both ML and AP increase with pixel index

        # Coordinate system for the REGISTERED image (physical units = IBL bregma um)
        brain_coordinates_warp = BrainCoordinates(
            [self.registered_image.shape[1], self.registered_image.shape[0], 2],  # [width, height, 2]
            xyz0=warp_origin_coords_um,
            dxyz=[image_resolution, image_resolution, image_resolution],
        )

        # Coordinate system for the ATLAS PROJECTION image (shares physical frame with warp)
        brain_coordinates_reference = BrainCoordinates(
            [self.atlas_projection.shape[1], self.atlas_projection.shape[0], 2],  # [width, height, 2]
            xyz0=reference_origin_coords_um,
            dxyz=[reference_resolution, reference_resolution, reference_resolution],
        )

        # Build a flat list of all pixel indices for the registered image.
        # meshgrid produces x_index[row,col]=col and y_index[row,col]=row.
        x_index, y_index = np.meshgrid(
            np.arange(self.registered_image.shape[1]),  # column indices (x)
            np.arange(self.registered_image.shape[0]),  # row indices (y)
        )
        coords_flat = np.column_stack((x_index.ravel(), y_index.ravel()))  # shape (H*W, 2): [col, row] per pixel

        # Append z=0 to make 3-D pixel indices required by BrainCoordinates.i2xyz
        zeros = np.zeros((coords_flat.shape[0], 1), dtype=coords_flat.dtype)
        coords_flat = np.hstack((coords_flat, zeros))  # shape (H*W, 3)

        # Convert every registered-image pixel → physical IBL bregma coords in um
        # xyz_um shape: (H*W, 3), columns: [ML_um, AP_um, DV_um]
        xyz_um = brain_coordinates_warp.i2xyz(coords_flat)

        # For each registered-image pixel, find the corresponding atlas-projection pixel.
        # mode="clip" clamps out-of-bounds queries to the image edge instead of raising an error.
        # NOTE: this lookup is only spatially correct when both BrainCoordinates share the same physical frame.
        ref_idx = brain_coordinates_reference.xyz2i(xyz_um, mode="clip")  # shape (H*W, 3): [col, row, z] in atlas

        # Convert IBL bregma coords (um) → Allen CCF coords (um) via iblatlas.
        # xyz2ccf input: metres, IBL RAS convention.  output: um, axis order = [AP, DV, ML].
        # NOTE: this is the same conversion used in _build_landmark_coordinate_tables,
        # so the per-pixel CCF values should match the per-landmark CCF table values
        # at the landmark pixel locations — if warp_origin_coords_um is correct.
        atlas = AllenAtlas(res_um=10)
        xyz_m = xyz_um * 1e-6  # um → metres (required by atlas.xyz2ccf)
        # iblatlas.xyz2ccf expects RAS convention (y = +anterior).
        # In this dataset y increases posteriorly, so negate y before converting.
        xyz_m_for_ccf = xyz_m.copy()
        xyz_m_for_ccf[:, 1] = -xyz_m_for_ccf[:, 1]
        ccf_um = atlas.xyz2ccf(xyz=xyz_m_for_ccf, ccf_order="apdvml", mode="clip").astype(np.float64)  # shape (H*W, 3)

        # Look up the atlas region label at each atlas-projection pixel.
        # ref_idx[:,0] = column (x), ref_idx[:,1] = row (y) in atlas_projection.
        # atlas_projection values are integer region labels (not Allen IDs yet).
        regions = self.atlas_projection[ref_idx[:, 1], ref_idx[:, 0]]  # shape (H*W,)

        # Reshape flat arrays back to 2-D / 3-D image shapes
        regions_image = regions.reshape(self.registered_image.shape[0], self.registered_image.shape[1])  # (H, W)
        xyz_um_image = xyz_um.reshape(self.registered_image.shape[0], self.registered_image.shape[1], 3)  # (H, W, 3)
        ccf_um_image = ccf_um.reshape(self.registered_image.shape[0], self.registered_image.shape[1], 3)  # (H, W, 3)

        # Build lookup: atlas label → Allen structure ID and acronym
        label_to_allen_id = self.ccf_regions.set_index("label")["allen_id"].to_dict()
        brain_region_id_image = np.vectorize(label_to_allen_id.get)(
            regions_image
        )  # maps each pixel label → Allen ID (or None)

        # Pixels with no matching label (background) become 0
        outside_mask = brain_region_id_image == None  # noqa: E711
        brain_region_id_image[outside_mask] = 0

        label_to_acronym = self.ccf_regions.set_index("label")["acronym"].to_dict()
        brain_region_acronym_image = np.vectorize(label_to_acronym.get)(
            regions_image
        )  # maps each pixel label → acronym string
        brain_region_acronym_image[outside_mask] = "out-of-atlas"

        registered_image = nwbfile.processing["ophys"]["Images"]["RegisteredImage"]  # link to the NWB image object

        one_photon_series = None
        # Processed data doesn't have raw one photon series data.
        if "OnePhotonSeriesCalcium" in nwbfile.acquisition:
            one_photon_series = nwbfile.acquisition["OnePhotonSeriesCalcium"]

        # Per-pixel IBL bregma coordinates (um) for the registered image
        ibl_anatomical_coordinates_image = AnatomicalCoordinatesImage(
            name="AnatomicalCoordinatesImageIBLBregma",
            description="Estimated coordinates for each pixel of the registered image in IBL bregma-centered coordinate system.",
            space=self.ibl_bregma_space,
            method="IBL manual annotation",  # TODO: confirm method description
            image=registered_image,
            localized_entity=one_photon_series,  # link to the source of the coordinates
            x=xyz_um_image[:, :, 0],  # ML_um per pixel
            y=xyz_um_image[:, :, 1],  # AP_um per pixel
            z=xyz_um_image[:, :, 2],  # DV_um per pixel (all 0 for dorsal projection)
            brain_region=brain_region_acronym_image,
        )

        # Per-pixel Allen CCF coordinates (um, AP/DV/ML) for the registered image.
        # NOTE: ccf_um_image is derived from xyz_um → xyz_m → atlas.xyz2ccf.
        # It should match AnatomicalCoordinatesTableCCFv3 at landmark pixel positions
        # unless warp_origin_coords_um (or reference_origin_coords_um) is wrong.
        ccf_anatomical_coordinates_image = AnatomicalCoordinatesImage(
            name="AnatomicalCoordinatesImageCCFv3",
            description="Estimated coordinates for each pixel of the registered image in CCFv3 coordinate system.",
            space=self.allen_ccf_space,
            method="IBL manual annotation",  # TODO: confirm method description
            image=registered_image,
            localized_entity=one_photon_series,  # link to the source of the coordinates
            x=ccf_um_image[:, :, 0],  # AP_um per pixel
            y=ccf_um_image[:, :, 1],  # DV_um per pixel
            z=ccf_um_image[:, :, 2],  # ML_um per pixel
            brain_region=brain_region_acronym_image,
        )
        return ibl_anatomical_coordinates_image, ccf_anatomical_coordinates_image, brain_region_id_image

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
        # Find all non-zero (in-atlas) pixels in the registered image
        ys, xs = brain_region_id_image.nonzero()
        registered_masks = BrainRegionMasks(
            name="RegisteredImageBrainRegionMasksIBLBregma",
            description="Brain region masks for each pixel in the registered image based on the atlas projection.",
        )
        for y, x in zip(ys, xs):
            registered_masks.add_row(
                x=int(x), y=int(y), brain_region_id=int(brain_region_id_image[y, x]), check_ragged=False
            )

        # Warp the integer Allen-ID image back into source-image space using the inverse affine.
        # order=0 = nearest-neighbour interpolation, which preserves discrete integer IDs
        # (higher-order interpolation would blend IDs between regions).
        source_brain_region_id_image = warp(
            brain_region_id_image.astype(np.float64),
            inverse_map=self.landmarks["transform"].inverse,  # inverse of source→registered transform
            output_shape=self.source_image.shape,
            order=0,  # nearest-neighbour: no blending of region IDs
            preserve_range=True,
        ).astype(np.int64)

        ys_src, xs_src = (source_brain_region_id_image != 0).nonzero()  # non-zero = in-atlas pixels in source space
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

        # landmarks["landmarks"][["x","y"]] is bregma-relative in mm.
        # Divide by 1000 → metres (required by atlas.xyz2ccf).
        xy_m = self.landmarks["landmarks"][["x", "y"]].values.astype(float) / 1000.0  # mm → m
        xyz_m = np.hstack((xy_m, np.zeros((xy_m.shape[0], 1), dtype=float)))  # append z=0 (dorsal surface)
        xyz_um_landmarks = xyz_m * 1e6  # m → um, used for the IBL bregma table

        # Convert landmark bregma coords (metres) → Allen CCF coords (um).
        # atlas.xyz2ccf input: metres, IBL RAS (x=ML, y=AP, z=DV).
        # output with ccf_order="apdvml": columns = [AP_um, DV_um, ML_um].
        # NOTE: no mode= argument here (defaults to "raise"), unlike the image path which uses mode="clip".
        # KEY: these CCF values come directly from landmarks["landmarks"] mm coords.
        # The CCF values in AnatomicalCoordinatesImageCCFv3 come from per-pixel BrainCoordinates→xyz2ccf.
        # Both use the same atlas.xyz2ccf call, so they should agree at landmark pixel positions
        # — unless BrainCoordinates introduces an offset (see ⚠ in _build_anatomical_coordinates_image).
        atlas = AllenAtlas(res_um=10)
        # iblatlas.xyz2ccf expects RAS convention (y = +anterior).
        # In this dataset y increases posteriorly, so negate y before converting.
        xyz_m_for_ccf = xyz_m.copy()
        xyz_m_for_ccf[:, 1] = -xyz_m_for_ccf[:, 1]
        ccf_um = atlas.xyz2ccf(xyz=xyz_m_for_ccf, ccf_order="apdvml").astype(np.float64)  # shape (N, 3)

        for landmark_index in range(len(landmarks)):
            brain_region = landmarks["landmark_labels"][landmark_index]

            ibl_bregma_coordinates_table.add_row(
                x=xyz_um_landmarks[landmark_index, 0],  # ML_um
                y=xyz_um_landmarks[landmark_index, 1],  # AP_um
                z=xyz_um_landmarks[landmark_index, 2],  # DV_um (0 for all landmarks on dorsal surface)
                brain_region=brain_region,
                localized_entity=landmark_index,  # index into the Landmarks table
            )
            ccf_coordinates_table.add_row(
                x=ccf_um[landmark_index, 0],  # AP_um in CCF
                y=ccf_um[landmark_index, 1],  # DV_um in CCF
                z=ccf_um[landmark_index, 2],  # ML_um in CCF
                brain_region=brain_region,
                localized_entity=landmark_index,  # index into the Landmarks table
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
        ibl_anatomical_coordinates_image, ccf_anatomical_coordinates_image, brain_region_id_image = (
            self._build_anatomical_coordinates_image(
                nwbfile=nwbfile,
                landmarks=landmarks,
            )
        )
        localization.add_anatomical_coordinates_images(
            [ibl_anatomical_coordinates_image, ccf_anatomical_coordinates_image]
        )

        # Build BrainRegionMasks for registered and source spaces
        registered_masks, source_masks = self._build_brain_region_masks(brain_region_id_image=brain_region_id_image)
        localization.add_brain_region_masks([registered_masks, source_masks])

        # Assemble AtlasRegistration
        # Now that all linked objects exist (AnatomicalCoordinatesImage +
        # BrainRegionMasks are owned by Localization), AtlasRegistration can
        # hold links to them alongside the affine transform and landmarks.
        ophys = get_module(nwbfile=nwbfile, name="ophys")
        source_image = ophys[summary_images_name][source_image_name]
        registered_image = ophys["Images"]["RegisteredImage"]
        atlas_projection = ophys["Images"]["AtlasProjectionImage"]

        affine_transformation = AffineTransformation(
            name="AffineTransformation",
            affine_matrix=self.landmarks["transform"].params,  # 3×3 homogeneous matrix of the skimage AffineTransform
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
        summary_images_name: str = "Images",
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
        summary_images_name : str, default: "Images"
            Name of the container in the NWB file that holds the summary images.
        source_image_name : str, default: "MeanImage"
            Name of the source image within the summary images' container.
        """

        self.add_atlas_registration_to_nwbfile(
            nwbfile=nwbfile,
            summary_images_name=summary_images_name,
            source_image_name=source_image_name,
        )
