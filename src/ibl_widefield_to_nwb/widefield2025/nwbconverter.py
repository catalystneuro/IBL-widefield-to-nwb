"""Primary NWBConverter class for this dataset."""

from neuroconv import NWBConverter

from ibl_widefield_to_nwb.widefield2025.datainterfaces import WidefieldImagingInterface


class WidefieldRawNWBConverter(NWBConverter):
    """Primary conversion class for Widefield raw imaging data."""

    data_interface_classes = dict(
        ImagingBlue=WidefieldImagingInterface,
        ImagingViolet=WidefieldImagingInterface,
    )
