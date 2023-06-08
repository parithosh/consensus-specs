from eth2spec.test.helpers.block import (
    build_empty_block_for_next_slot, build_empty_block
)
from eth2spec.test.context import (
    spec_state_test,
    with_whisk_and_later,
    WHISK,
)
from eth2spec.test.helpers.keys import privkeys, pubkeys, whisk_ks_initial
from eth2spec.test.helpers.state import (
    state_transition_and_sign_block
)
from curdleproofs import IsValidWhiskShuffleProof
from eth2spec.test.helpers.whisk import is_first_proposal, get_whisk_tracker_and_commitment, set_as_first_proposal
from curdleproofs import WhiskTracker

known_whisk_trackers = {}


def assign_proposer_at_slot(state, slot: int):
    state


def initialize_whisk_full(spec, state):
    # TODO: De-duplicate code from whisk/fork.md
    for index, validator in enumerate(state.validators):
        whisk_k_commitment, whisk_tracker = spec.get_initial_commitments(whisk_ks_initial[index])
        validator.whisk_k_commitment = whisk_k_commitment
        validator.whisk_tracker = whisk_tracker

    # Do a candidate selection followed by a proposer selection so that we have proposers for the upcoming day
    # Use an old epoch when selecting candidates so that we don't get the same seed as in the next candidate selection
    spec.select_whisk_candidate_trackers(state, spec.Epoch(0))
    spec.select_whisk_proposer_trackers(state, spec.Epoch(0))

# Fill candidate trackers with the same tracker so shuffling does not break
def fill_candidate_trackers(spec, state, tracker: WhiskTracker):
    for i in range(spec.WHISK_CANDIDATE_TRACKERS_COUNT):
        state.whisk_candidate_trackers[i] = tracker

@with_whisk_and_later
@spec_state_test
def test_whisk__process_block_single_initial(spec, state):
    assert state.slot == 0
    proposer_slot_1 = 0
    tracker_slot_1, k_commitment = get_whisk_tracker_and_commitment(whisk_ks_initial[proposer_slot_1], 1)
    state.validators[proposer_slot_1].whisk_k_commitment = k_commitment
    state.whisk_proposer_trackers[1] = tracker_slot_1
    fill_candidate_trackers(spec, state, tracker_slot_1)

    # Produce and process a whisk block
    yield 'pre', state

    block = build_empty_block(spec, state, 1, proposer_slot_1)
    signed_block = state_transition_and_sign_block(spec, state, block)

    yield 'blocks', [signed_block]
    yield 'post', state
