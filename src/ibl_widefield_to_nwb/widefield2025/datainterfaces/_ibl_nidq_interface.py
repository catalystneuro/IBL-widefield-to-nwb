from neuroconv.datainterfaces import SpikeGLXNIDQInterface

from ibl_widefield_to_nwb.widefield2025.datainterfaces._base_ibl_interface import (
    BaseIBLDataInterface,
)


class IblNIDQInterface(SpikeGLXNIDQInterface, BaseIBLDataInterface):

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Get data requirements for NIDQ interface.

        Returns
        -------
        dict
            Dictionary with required NIDQ files including wiring.json.
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.cbin",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.meta",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.ch",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json",
                ],
            },
        }
