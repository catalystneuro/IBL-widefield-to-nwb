from typing import Optional

PROTOCOLS_MAPPING = {
    "cuedBiasedChoiceWorld": {
        "protocol_type": "active",
        "protocol_description": (
            "Cued biased choice world — a custom variant of the biased choice world task with added visual cues. "
            "The mouse performs a decision-making task: a Gabor patch appears on the left or right of the screen, "
            "and the mouse turns a steering wheel to bring it to the center. Correct responses are rewarded with water. "
            "Stimulus probability alternates between 80/20 and 20/80 blocks. All contrast levels are used "
            "(100%, 25%, 12.5%, 6.25%, 0%)."
        ),
    },
    "biasedChoiceWorld": {
        "protocol_type": "active",
        "protocol_description": (
            "Biased choice world — the standard IBL data-collection task for trained mice. "
            "A Gabor patch appears at ±35° azimuth and the mouse turns a wheel to bring it to the center. "
            "Correct responses earn a water reward (~1.5 µL); incorrect responses trigger white noise and a 2s timeout. "
            "Stimulus probability alternates between 80/20 and 20/80 blocks (starting with a 50/50 block), "
            "with block lengths drawn from a truncated exponential distribution (min 20, max 100 trials). "
            "Full contrast set: [1.0, 0.25, 0.125, 0.0625, 0.0]. "
        ),
    },
    "advancedChoiceWorld": {
        "protocol_type": "active",
        "protocol_description": (
            "Advanced choice world — the iblrig v8+ replacement for biasedChoiceWorld. "
            "Functionally equivalent to biasedChoiceWorld (same biased block structure, contrast set, and trial logic) "
            "but with updated software architecture using Bonsai for visual stimulus rendering and an improved "
            "Bpod state machine integration."
        ),
    },
    "passiveChoiceWorld": {
        "protocol_type": "passive",
        "protocol_description": (
            "Passive choice world — replay of choice world stimuli without behavioral contingency. "
            "Gabor patches at all contrasts and positions, go cue tones, and white noise bursts are presented "
            "in randomized order while the mouse is head-fixed but not performing any task. "
            "No reward is delivered and no response is required. "
            "Used to compare neural responses during active decision-making vs. passive viewing, "
            "isolating sensory from decision- and movement-related signals."
        ),
    },
    "sparseNoise": {
        "protocol_type": "passive",
        "protocol_description": (
            "Sparse noise stimulus for receptive field mapping. "
            "Sparse white and black squares are presented at random screen locations to map the spatial "
            "receptive fields of visually responsive neurons. Each frame contains a small number of "
            "active squares on a gray background, allowing efficient estimation of spatial receptive fields."
        ),
    },
    "passiveVideo": {
        "protocol_type": "passive",
        "protocol_description": (
            "Passive video presentation — typically a Perlin noise video (spatio-temporal noise pattern) "
            "played to the mouse for retinotopic mapping and visual cortex characterization. "
            "No behavioral contingency — the mouse simply views the screen. "
        ),
    },
    "spontaneous": {
        "protocol_type": "passive",
        "protocol_description": (
            "Spontaneous activity recording — no stimuli or task. "
            "A gray screen is displayed while neural activity is recorded. "
            "Used to characterize baseline neural dynamics, ongoing activity, and resting-state patterns. "
            "Typically lasts 5-10 minutes."
        ),
    },
    "trainingChoiceWorld": {
        "protocol_type": "training",
        "protocol_description": (
            "Training choice world — the standard IBL training task. "
            "Mice learn to turn a wheel to move a Gabor patch to the center of the screen. "
            "Uses adaptive contrast levels: training starts with only high-contrast stimuli (100%) "
            "and progressively introduces harder contrasts (25%, 12.5%, 6.25%, 0%) as performance improves. "
            "No probability blocks — stimulus appears 50/50 left/right throughout. "
            "The mouse progresses through training stages until meeting criteria for the biased task."
        ),
    },
    "trainingPhaseChoiceWorld": {
        "protocol_type": "training",
        "protocol_description": (
            "Training phase choice world — the iblrig v8+ replacement for trainingChoiceWorld. "
            "Same adaptive training progression (phases 0-5) with Bonsai-based visual stimulus rendering. "
            "Phase transitions are based on performance metrics identical to trainingChoiceWorld criteria."
        ),
    },
    "habituationChoiceWorld": {
        "protocol_type": "habituation",
        "protocol_description": (
            "Habituation choice world — pre-training habituation task. "
            "Mice are exposed to the rig environment, visual stimuli, and reward delivery "
            "without requiring any wheel turns. The stimulus moves to the center automatically "
            "and water is delivered freely on every trial. Only high-contrast stimuli (100%) are used. "
            "Typically runs for 1-3 days before formal training begins."
        ),
    },
    "ephysChoiceWorld": {
        "protocol_type": "active",
        "protocol_description": (
            "Electrophysiology choice world — biasedChoiceWorld configured for sessions with "
            "simultaneous Neuropixels electrophysiology recordings. Behaviorally identical to biasedChoiceWorld "
            "but with additional synchronization signals for alignment with neural recordings."
            "A Gabor patch appears at ±35° azimuth and the mouse turns a wheel to bring it to the center. "
            "Correct responses earn a water reward (~1.5 µL); incorrect responses trigger white noise and a 2s timeout. "
            "Stimulus probability alternates between 80/20 and 20/80 blocks (starting with a 50/50 block), "
            "with block lengths drawn from a truncated exponential distribution (min 20, max 100 trials). "
            "Full contrast set: [1.0, 0.25, 0.125, 0.0625, 0.0]. "
        ),
    },
    "widefieldChoiceWorld": {
        "protocol_type": "active",
        "protocol_description": (
            "Widefield choice world — biasedChoiceWorld configured for sessions with "
            "simultaneous widefield imaging recordings. Behaviorally identical to biasedChoiceWorld "
            "but with additional synchronization signals for alignment with neural recordings."
            "A Gabor patch appears at ±35° azimuth and the mouse turns a wheel to bring it to the center. "
            "Correct responses earn a water reward (~1.5 µL); incorrect responses trigger white noise and a 2s timeout. "
            "Stimulus probability alternates between 80/20 and 20/80 blocks (starting with a 50/50 block), "
            "with block lengths drawn from a truncated exponential distribution (min 20, max 100 trials). "
            "Full contrast set: [1.0, 0.25, 0.125, 0.0625, 0.0]. "
        ),
    },
    "tonotopicMapping": {
        "protocol_type": "passive",
        "protocol_description": (
            "Tonotopic mapping — presents auditory stimuli at different frequencies "
            "to map the tonotopic organization of auditory cortex. "
            "Used alongside mesoscope imaging for characterizing auditory responses."
        ),
    },
}


def get_protocol_type_and_description(protocol_name: str) -> Optional[tuple[str, str]]:
    """
    Get protocol type and description from the mapping.

    Parameters
    ----------
    protocol_name : str
        The name of the protocol to look up

    Returns
    -------
    tuple[str, str] or None
        A tuple with (protocol_type, protocol_description) if found, else None
    """
    # NB: the actual protocol name in the experiment description may have additional suffixes (e.g. "cuedBiasedChoiceWorld_1"), so we check for substrings
    for key, value in PROTOCOLS_MAPPING.items():
        if key in protocol_name:
            return value["protocol_type"], value["protocol_description"]
    return None
