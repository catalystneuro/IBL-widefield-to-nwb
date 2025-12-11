from warnings import warn

# =============================================================================
# Digital Device Labels (needed at init time for digital_channel_groups)
# These define how to interpret binary values (0/1) for each device type
# =============================================================================

DIGITAL_DEVICE_LABELS = {
    "left_camera": {0: "exposure_end", 1: "frame_start"},
    "right_camera": {0: "exposure_end", 1: "frame_start"},
    "body_camera": {0: "exposure_end", 1: "frame_start"},
    "imec_sync": {0: "sync_low", 1: "sync_high"},
    "frame2ttl": {0: "screen_dark", 1: "screen_bright"},
    "rotary_encoder_0": {0: "phase_low", 1: "phase_high"},
    "rotary_encoder_1": {0: "phase_low", 1: "phase_high"},
    "audio": {0: "audio_off", 1: "audio_on"},
}

# =============================================================================
# Functions to build NIDQ metadata from wiring configuration
# Adapted from https://github.com/h-mayorquin/IBL-to-nwb/blob/4fed77ec79e1b73c31a5c7e927b40e26256ed056/src/ibl_to_nwb/datainterfaces/_ibl_nidq_interface.py
# =============================================================================


def _get_analog_channel_groups_from_wiring(wiring: dict[str, str]) -> dict[str, dict]:
    """
    Get analog channel groups from wiring configuration.


    Parameters
    ----------
    wiring: dict[str, str]
        Wiring configuration from `_spikeglx_ephysData_g0_t0.nidq.wiring.json` file loaded as a dictionary.

    Returns
    -------
    dict[str, list[str]]
        Mapping from device names to lists of SpikeGLX analog channel IDs that are specified in the wiring configuration.
        Example: {"bpod": {"channels": ["nidq#XA0"]}}

    """
    analog_channel_groups = {}

    analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})
    for analog_input, device_name in analog_wiring.items():
        if analog_input.startswith("AI"):
            channel_num = analog_input[2:]
            channel_id = f"nidq#XA{channel_num}"
            analog_channel_groups[device_name] = {"channels": [channel_id]}

    return analog_channel_groups


def _get_digital_channel_groups_from_wiring(wiring: dict[str, str]) -> dict[str, dict]:
    """
    Get digital channel groups from wiring configuration.

    Parameters
    ----------
    wiring: dict[str, str]
        Wiring configuration from `_spikeglx_ephysData_g0_t0.nidq.wiring.json` file loaded as a dictionary.

    Returns
    -------
    dict[str, list[str]]
        Mapping from device names to lists of SpikeGLX digital channel IDs that are specified in the wiring configuration.
        Example: {"left_camera": {"channels": ["nidq#XD0"]}}

    """
    digital_channel_groups = {}

    digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})
    for port_pin, device_name in digital_wiring.items():
        if port_pin.startswith("P0."):
            bit_num = port_pin.split(".")[-1]
            channel_id = f"nidq#XD{bit_num}"

            if device_name in DIGITAL_DEVICE_LABELS:
                digital_channel_groups[device_name] = {
                    "channels": {channel_id: {"labels_map": DIGITAL_DEVICE_LABELS[device_name]}}
                }
            else:
                warn(
                    f"No labels configured for digital device '{device_name}' "
                    f"at channel {channel_id} (port {port_pin}). "
                    f"Add an entry to DIGITAL_DEVICE_LABELS in src/widefield2025/utils/_nidq_wiring.py.",
                    UserWarning,
                    stacklevel=2,
                )

    return digital_channel_groups


def _build_nidq_metadata_from_wiring(
    wiring: dict,
    device_metadata: dict,
    metadata_key: str = "SpikeGLXNIDQ",
) -> dict:
    """
    Build NIDQ metadata dynamically based on wiring configuration.

    Parameters
    ----------
    wiring : dict
        Wiring configuration from `_spikeglx_ephysData_g0_t0.nidq.wiring.json` file.
        Expected structure:
        {
            "SYNC_WIRING_DIGITAL": {"P0.0": "left_camera", "P0.1": "right_camera", ...},
            "SYNC_WIRING_ANALOG": {"AI0": "bpod", "AI1": "laser", ...}
        }
    device_metadata : dict
        Device/sensor metadata organized by device name. Expected structure (from _metadata/widefield_nidq_metadata.yaml):
        {
            "TimeSeries": {"SpikeGLXNIDQ": {"bpod": {...}, ...}},
            "Events": {"SpikeGLXNIDQ": {"left_camera": {...}, ...}}
        }
    metadata_key : str, optional
        Key used to organize TimeSeries and Events metadata in the device_metadata dictionary. Default is "SpikeGLXNIDQ".

    Returns
    -------
    dict
        Metadata dictionary structured for neuroconv with channel IDs as keys:
        {
            "TimeSeries": {"SpikeGLXNIDQ": {"bpod": {"name": "...", "description": "..."}}},
            "Events": {"SpikeGLXNIDQ": {"left_camera": {"name": "...", "description": "...", "meanings": {...}}}}
        }
    """
    # Initialize metadata structure
    nidq_metadata = {"TimeSeries": {metadata_key: {}}, "Events": {metadata_key: {}}}

    # Map analog signals (TimeSeries)
    analog_signals_metadata = device_metadata.get("TimeSeries", {})
    analog_channel_groups = _get_analog_channel_groups_from_wiring(wiring=wiring)
    for device_name in analog_channel_groups:
        if device_name in analog_signals_metadata:
            nidq_metadata["TimeSeries"][metadata_key][device_name] = analog_signals_metadata[device_name]

    # Map digital signals (Events)
    digital_signals_metadata = device_metadata.get("Events", {})
    digital_channel_groups = _get_digital_channel_groups_from_wiring(wiring=wiring)
    for device_name in digital_channel_groups:
        if device_name in digital_signals_metadata:
            nidq_metadata["Events"][metadata_key][device_name] = digital_signals_metadata[device_name]

    return nidq_metadata
