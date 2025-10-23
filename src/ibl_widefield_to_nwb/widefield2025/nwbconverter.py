"""Primary NWBConverter class for this dataset."""
from neuroconv import NWBConverter

from src.ibl_widefield_to_nwb.widefield2025 import WidefieldSegmentationInterface, WidefieldImagingInterface


class Widefield2025NWBConverter(NWBConverter):
    """Primary conversion class for Widefield data."""

    data_interface_classes = dict(
        ImagingBlue=WidefieldImagingInterface,
        ImagingViolet=WidefieldImagingInterface,
        SegmentationBlue=WidefieldSegmentationInterface,
        SegmentationViolet=WidefieldSegmentationInterface,
    )

    def temporally_align_data_interfaces(self, metadata: dict | None = None, conversion_options: dict | None = None):
        for imaging_interface_name, segmentation_interface_name in [
            ("ImagingBlue", "SegmentationBlue"),
            ("ImagingViolet", "SegmentationViolet"),
        ]:
            segmentation_interface = self.data_interface_objects[segmentation_interface_name]
            native_timestamps = segmentation_interface.segmentation_extractor.get_native_timestamps()
            imaging_interface = self.data_interface_objects[imaging_interface_name]
            imaging_interface.set_aligned_timestamps(aligned_timestamps=native_timestamps)
