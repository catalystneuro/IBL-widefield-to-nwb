# The create_channel_name_mapping function was copied from https://github.com/h-mayorquin/IBL-to-nwb/blob/d7303e64194ad6b56fc0e51eee9d1aa71607ce62/src/ibl_to_nwb/utils/nidq_wiring.py
# The method was renamed to _create_channel_name_mapping and modified to include 'nidq#' prefix in channel IDs


def _create_channel_name_mapping(wiring: dict | None) -> dict[str, str]:
    """
    Create a mapping from SpikeGLX channel IDs to meaningful device names.

    SpikeGLX uses technical channel identifiers (XD0, XD1, XA0, etc.) while
    the wiring.json provides semantic names (left_camera, bpod, etc.). This
    function creates a mapping between them.

    Parameters
    ----------
    wiring : dict or None
        Wiring configuration from load_nidq_wiring()

    Returns
    -------
    dict[str, str]
        Mapping from SpikeGLX channel IDs to device names.
        Example: {'XD0': 'left_camera', 'XD1': 'right_camera', 'XA0': 'bpod'}
        Returns empty dict if wiring is None.

    Notes
    -----
    Digital channel mapping:
    - P0.0 -> XD0 (bit 0 of digital port)
    - P0.1 -> XD1 (bit 1 of digital port)
    - ... up to P0.7 -> XD7

    Analog channel mapping:
    - AI0 -> XA0
    - AI1 -> XA1
    - AI2 -> XA2
    """
    if wiring is None:
        return {}

    channel_mapping = {}

    # Map digital channels (P0.0-P0.7 -> XD0-XD7)
    digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})
    for port_pin, device_name in digital_wiring.items():
        # Extract bit number from port pin (e.g., "P0.3" -> 3)
        if port_pin.startswith("P0."):
            bit_num = port_pin.split(".")[-1]
            channel_id = f"nidq#XD{bit_num}"
            channel_mapping[channel_id] = device_name

    # Map analog channels (AI0-AI2 -> XA0-XA2)
    analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})
    for analog_input, signal_name in analog_wiring.items():
        # Extract channel number from analog input (e.g., "AI0" -> 0)
        if analog_input.startswith("AI"):
            channel_num = analog_input[2:]  # Get number after 'AI'
            channel_id = f"nidq#XA{channel_num}"
            channel_mapping[channel_id] = signal_name

    return channel_mapping


def _get_analog_channel_groups_from_wiring(wiring: dict[str, str]) -> dict[str, list[str]]:
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
        Example: {'bpod': ['nidq#XA0']}

    """
    channel_name_mapping = _create_channel_name_mapping(wiring=wiring)
    analog_channel_groups = {}
    for k, v in channel_name_mapping.items():
        if "nidq#XA" in k:
            analog_channel_groups.setdefault(v, []).append(k)
    return analog_channel_groups


def _build_nidq_metadata_from_wiring(wiring: dict, device_metadata: dict) -> dict:
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
        Device/sensor metadata organized by device name (from _metadata/widefield_nidq_metadata.yaml).
        Expected structure:
        {
            "AnalogSignals": {"bpod": {"name": "...", "description": "..."}, ...},
            "DigitalSignals": {"left_camera": {"name": "...", "description": "...", "labels_map": {...}}, ...}
        }

    Returns
    -------
    dict
        Metadata dictionary structured for neuroconv with channel IDs as keys:
        {
            "TimeSeries": {"SpikeGLXNIDQ": {"bpod": {"name": "...", "description": "..."}}},
            "Events": {"SpikeGLXNIDQ": {"nidq#XD0": {"name": "...", "description": "...", "labels_map": {...}}}}
        }
    """
    # Get channel to device mapping
    channel_name_mapping = _create_channel_name_mapping(wiring=wiring)

    # Initialize metadata structure
    nidq_metadata = {"TimeSeries": {"SpikeGLXNIDQ": {}}, "Events": {"SpikeGLXNIDQ": {}}}

    # Map analog signals (TimeSeries)
    analog_signals_metadata = device_metadata.get("AnalogSignals", {})
    analog_channels = [
        (channel_id, device_name) for channel_id, device_name in channel_name_mapping.items() if "nidq#XA" in channel_id
    ]
    for channel_id, device_name in analog_channels:
        if device_name in analog_signals_metadata:
            nidq_metadata["TimeSeries"]["SpikeGLXNIDQ"][device_name] = analog_signals_metadata[device_name]

    # Map digital signals (Events)
    digital_signals_metadata = device_metadata.get("DigitalSignals", {})
    digital_channels = [
        (channel_id, device_name) for channel_id, device_name in channel_name_mapping.items() if "nidq#XD" in channel_id
    ]
    for channel_id, device_name in digital_channels:
        if device_name in digital_signals_metadata:
            # Use channel_id as the key for digital signals (Events)
            nidq_metadata["Events"]["SpikeGLXNIDQ"][channel_id] = digital_signals_metadata[device_name]

    return nidq_metadata
